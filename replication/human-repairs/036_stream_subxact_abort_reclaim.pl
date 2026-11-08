# Copyright (c) 2026, PostgreSQL Global Development Group
#
# src/test/subscription/t/036_stream_subxact_abort_reclaim.pl
#
# Test that a ROLLBACK TO SAVEPOINT of a streamed subtransaction is reflected
# on the subscriber when the leader apply worker switches to serializing
# changes to a file (partial serialization) while the parallel apply worker
# is blocked, and that reclaiming the spooled space of the aborted batch
# keeps the spool file well-formed when it spans more than one stream block.

use strict;
use warnings FATAL => 'all';
use PostgreSQL::Test::Cluster;
use PostgreSQL::Test::Utils;
use Test::More;

my $SERIALIZE_LOG = qr/LOG: ( [A-Z0-9]+:)? logical replication apply worker will serialize the remaining changes of remote transaction \d+ to a file/;
my $RECLAIM_LOG = qr/DEBUG:\s+reclaimed \d+ bytes from partial stream for transaction \d+/;

my $node_publisher = PostgreSQL::Test::Cluster->new('publisher');
$node_publisher->init(allows_streaming => 'logical');
$node_publisher->append_conf('postgresql.conf',
	'debug_logical_replication_streaming = immediate');
$node_publisher->start;

my $node_subscriber = PostgreSQL::Test::Cluster->new('subscriber');
$node_subscriber->init;
# We need DEBUG logs to observe savepoint definitions and space reclamation.
$node_subscriber->append_conf('postgresql.conf', 'log_min_messages = debug1');
$node_subscriber->start;

my $appname = 'tap_sub';

$node_publisher->safe_psql('postgres',
	"CREATE TABLE ledger (a int primary key, b int, payload text); "
	  . 'CREATE TABLE gate (a int primary key)');
$node_publisher->safe_psql('postgres',
	'CREATE PUBLICATION tap_pub FOR TABLE ledger, gate');

$node_subscriber->safe_psql('postgres',
	'CREATE TABLE gate (a int primary key); CREATE TABLE ledger (a int primary key, b int, payload text)');

$node_subscriber->safe_psql(
	'postgres',
	"CREATE SUBSCRIPTION $appname CONNECTION '"
	  . $node_publisher->connstr
	  . " dbname=postgres application_name=$appname' PUBLICATION tap_pub WITH (streaming = parallel, copy_data = false)"
	);

# Wait for initial table sync to finish.
$node_subscriber->wait_for_subscription_sync($node_publisher, $appname);

my $offset = 0;

# Check that the subscriber log does not contain any error from the given
# offset on, which would indicate a protocol violation and an apply restart.
sub check_no_apply_errors
{
	my ($offset) = @_;
	my $log = PostgreSQL::Test::Utils::slurp_file($node_subscriber->logfile);
	unlike(substr($log, $offset), qr/\b(ERROR|FATAL|PANIC):/,
		'no errors in the subscriber log');
}

# The publisher session that drives the streamed transaction.
my $writer = $node_publisher->background_psql('postgres');

sub flush
{
	$writer->query(q{SELECT pg_logical_emit_message(false, 'flush', '', true)});
}

###############################################
# 1. The parallel apply worker applies changes of the subtransaction and is
#    then blocked, so the leader switches to serializing changes to a file.
#    The ROLLBACK TO SAVEPOINT must still be applied on the subscriber even
#    though the spooled DML of the aborted subtransaction is reclaimed.
###############################################

$offset = -s $node_subscriber->logfile;

# Hold a lock on the subscriber that will block the parallel apply worker.
my $locker = $node_subscriber->background_psql('postgres');
$locker->query(q{BEGIN; LOCK TABLE gate IN ACCESS EXCLUSIVE MODE;});

$writer->query(q{BEGIN; INSERT INTO ledger VALUES (1, 10);});
flush();
$writer->query(q{SAVEPOINT sp; INSERT INTO ledger VALUES (2, 100);});
flush();

# The parallel apply worker has applied the subtransaction's change, so it
# has defined a savepoint for it.
$node_subscriber->wait_for_log(qr/DEBUG:\s+defining savepoint/, $offset);

# Block the parallel apply worker on the gate table.
$writer->query(q{INSERT INTO gate VALUES (1);});
flush();
$node_subscriber->poll_query_until(
	'postgres', q{
		SELECT 1 FROM pg_stat_subscription
		WHERE leader_pid IS NOT NULL
		  AND cardinality(pg_blocking_pids(pid)) > 0}, '1')
  or die 'Timed out waiting for the parallel apply worker to be blocked';

# The next change cannot be sent to the (blocked) parallel apply worker, so
# the leader serializes it to a file.
$writer->query(q{INSERT INTO ledger VALUES (3, 30, repeat('x', 20 * 1024 * 1024));});
flush();
$node_subscriber->wait_for_log($SERIALIZE_LOG, $offset);

# Reclaim the spooled DML of the aborted subtransaction.
$writer->query(q{ROLLBACK TO sp;});
flush();
$node_subscriber->wait_for_log($RECLAIM_LOG, $offset);

# Unblock the parallel apply worker; it applies the gate change inside the
# savepoint of the aborted subtransaction.
$locker->query(q{COMMIT;});

$writer->query(q{INSERT INTO ledger VALUES (4, 40);});
$writer->query(q{COMMIT;});
$node_publisher->wait_for_catchup($appname);

my $result = $node_subscriber->safe_psql('postgres',
	'SELECT a FROM ledger ORDER BY a; SELECT count(*) FROM gate');
is($result, qq(1\n4\n0),
	'check rollback to savepoint was reflected on subscriber after switching to partial serialization');

check_no_apply_errors($offset);
$writer->quit;
$locker->quit;

###############################################
# 2. The spooled DML of the aborted subtransaction spans more than one
#    stream block. Reclaiming it must not corrupt the spool file, which the
#    parallel apply worker replays at the end of the transaction.
###############################################

$node_subscriber->append_conf('postgresql.conf',
	'debug_logical_replication_streaming = immediate');
$node_subscriber->reload;
$node_subscriber->safe_psql('postgres', q{SELECT 1});

$offset = -s $node_subscriber->logfile;
$writer = $node_publisher->background_psql('postgres');

$writer->query(q{BEGIN; INSERT INTO ledger VALUES (5, 50);});
flush();
$writer->query(q{SAVEPOINT sp2; INSERT INTO ledger VALUES (6, 60);});
flush();
$writer->query(q{INSERT INTO ledger VALUES (7, 70);});
flush();
$node_subscriber->wait_for_log($SERIALIZE_LOG, $offset);

$writer->query(q{ROLLBACK TO sp2;});
flush();
$node_subscriber->wait_for_log($RECLAIM_LOG, $offset);

$writer->query(q{INSERT INTO ledger VALUES (8, 80);});
$writer->query(q{COMMIT;});
$node_publisher->wait_for_catchup($appname);

$result = $node_subscriber->safe_psql('postgres',
	'SELECT a FROM ledger ORDER BY a; SELECT count(*) FROM gate');
is($result, qq(1\n4\n5\n8\n0),
	'check rollback to savepoint spanning multiple spooled stream blocks was reflected on subscriber');

check_no_apply_errors($offset);
$writer->quit;

$node_subscriber->stop;
$node_publisher->stop;

done_testing();
