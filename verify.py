"""Independent result and plan checks using the supplied build's own server."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

SCHEMA = """
CREATE TABLE p(k int, label text) PARTITION BY LIST(k);
CREATE TABLE p_a PARTITION OF p FOR VALUES IN (1,2);
CREATE TABLE p_b PARTITION OF p FOR VALUES IN (10,20);
CREATE TABLE p_null PARTITION OF p FOR VALUES IN (NULL);
CREATE TABLE p_default PARTITION OF p DEFAULT;
INSERT INTO p VALUES (1,'a1'),(2,'a2'),(10,'b10'),(20,'b20'),
    (99,'keep'),(99,'drop'),(NULL,'nil'),(-7,'keep');

CREATE TABLE r(a int, b int) PARTITION BY RANGE(a,b);
CREATE TABLE r_explicit PARTITION OF r FOR VALUES FROM (13,0) TO (19,MAXVALUE);
CREATE TABLE r_default PARTITION OF r DEFAULT;
INSERT INTO r VALUES (19,5),(20,6),(32,-7),(32,-8),(18,0);
"""

LIST_CASES = [
    ('visible', "k = 20 OR (k = 99 AND label = 'keep')", [[20,'b20'],[99,'keep']], ['p_b','p_default']),
    ('default_first', "(k = -7 AND label = 'keep') OR k = 2", [[-7,'keep'],[2,'a2']], ['p_a','p_default']),
    ('default_only', "(k = 99 AND label = 'drop') OR (k = -7 AND label = 'keep')", [[-7,'keep'],[99,'drop']], ['p_default']),
    ('null_and_regular', "k IS NULL OR (k = 10 AND label = 'b10')", [[10,'b10'],[None,'nil']], ['p_b','p_null']),
    ('null_and_default', "k IS NULL OR (k = 99 AND label = 'keep')", [[99,'keep'],[None,'nil']], ['p_default','p_null']),
    ('two_regular', "k = 1 OR (k = 10 AND label = 'b10')", [[1,'a1'],[10,'b10']], ['p_a','p_b']),
    ('single_regular', "k = 1", [[1,'a1']], ['p_a']),
    ('nested_or', "(k = 20 OR (k = 99 AND label = 'keep')) AND label <> 'b20'", [[99,'keep']], ['p_b','p_default']),
]
RANGE_CASES = [
    ('range_default', 'a = 32 AND b >= -7', [[32,-7]], ['r_default']),
    ('range_explicit', 'a = 19 AND b >= 5', [[19,5]], ['r_explicit']),
    ('range_both', 'a >= 19 AND b >= 5', [[19,5],[20,6]], ['r_default','r_explicit']),
]
PARAM_CASES = [
    ('prepared_default', "20,99,'keep'", [[20,'b20'],[99,'keep']], ['p_b','p_default']),
    ('prepared_two_regular', "1,10,'b10'", [[1,'a1'],[10,'b10']], ['p_a','p_b']),
]
PREPARE = """PREPARE p_poll(int,int,text) AS
SELECT k,label FROM p WHERE k=$1 OR (k=$2 AND label=$3) ORDER BY k NULLS LAST,label;"""

def command(args, **kw):
    r=subprocess.run(args,text=True,capture_output=True,timeout=35,**kw)
    if r.returncode:
        raise RuntimeError(f'{Path(args[0]).name} exited {r.returncode}: {r.stderr[-1700:]}')
    return r.stdout

def relation_names(value, runtime=False):
    if isinstance(value, list):
        return set().union(*(relation_names(x,runtime) for x in value))
    if isinstance(value, dict):
        names=set()
        if 'Relation Name' in value and (not runtime or value.get('Actual Loops',0)>0):
            names.add(value['Relation Name'])
        for v in value.values():
            names.update(relation_names(v,runtime))
        return names
    return set()

def read_rows(s, numeric_value=False):
    return [[None if k=='' else int(k),int(v) if numeric_value else v] for k,v in (line.split('|') for line in s.splitlines())]

def check(bindir):
    with tempfile.TemporaryDirectory(prefix='slonik-prune-') as tmp:
        root=Path(tmp)
        data=root/'data'
        env={'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C', 'PGCONNECT_TIMEOUT':'4',
             'LD_LIBRARY_PATH':str(bindir.parent/'lib')}
        command([str(bindir/'initdb'),'-D',str(data),'-A','trust','-U','prune_audit','--no-locale','-E','UTF8'],env=env)
        ctl=[str(bindir/'pg_ctl'),'-D',str(data)]
        command([*ctl,'-l',str(root/'server.log'),'-o',f"-k {root} -c listen_addresses='' -c shared_buffers=24MB -c max_parallel_workers_per_gather=0",
                 '-w','-t','20','start'],env=env)
        psql=[str(bindir/'psql'),'-h',str(root),'-U','prune_audit','-d','postgres','-X','-w','-qAt','-v','ON_ERROR_STOP=1']
        def query(sql):
            return command([*psql,'-c',sql],env=env)
        try:
            query(SCHEMA)
            results=[]
            for table,cols,tests in [('p','k,label',LIST_CASES),('r','a,b',RANGE_CASES)]:
                for name,expr,expected,rels in tests:
                    sql=f'SELECT {cols} FROM {table} WHERE {expr} ORDER BY 1 NULLS LAST,2'
                    on=read_rows(query('SET enable_partition_pruning=on; '+sql),table=='r')
                    off=read_rows(query('SET enable_partition_pruning=off; '+sql),table=='r')
                    plan=sorted(relation_names(json.loads(query('EXPLAIN (FORMAT JSON, COSTS OFF) '+sql))))
                    rows_ok=on==off==expected
                    pruning_ok=plan==rels
                    results.append(dict(name=name, expected_rows=expected, actual_rows=on,
                                        unpruned_rows=off, expected_relations=rels, actual_relations=plan,
                                        rows_ok=rows_ok, pruning_ok=pruning_ok))
            for mode in ('force_custom_plan','force_generic_plan'):
                for name,args,expected,rels in PARAM_CASES:
                    pre=f'SET plan_cache_mode={mode}; '+PREPARE
                    sql=f'EXECUTE p_poll({args})'
                    on=read_rows(query(pre+sql))
                    off=read_rows(query('SET enable_partition_pruning=off; '+pre+sql))
                    plan=sorted(relation_names(json.loads(query(pre+'EXPLAIN (ANALYZE, FORMAT JSON, COSTS OFF) '+sql)),runtime=True))
                    results.append(dict(name=name+'_'+mode, expected_rows=expected, actual_rows=on, unpruned_rows=off,
                                        expected_relations=rels, actual_relations=plan, rows_ok=on==off==expected,
                                        pruning_ok=plan==rels))
            return dict(version=query('SHOW server_version').strip(), checks=results,
                        repro_pass=results[0]['rows_ok'], all_rows_match=all(x['rows_ok'] for x in results),
                        pruning_pass=all(x['pruning_ok'] for x in results))
        finally:
            command([*ctl,'-w','-t','20','stop','-m','fast'],env=env)

if __name__=='__main__':
    result=check(Path(sys.argv[1]))
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["all_rows_match"] and result["pruning_pass"] else 1)
