from pathlib import Path

def sandbox(work: Path, build: Path, helpers: Path, command: str):
    git_dir=['--ro-bind',str(work/'.git'),'/work/.git'] if (work/'.git').is_dir() else []
    return [
        '/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
        '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin',
        '--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
        '--symlink','usr/sbin','/sbin','--proc','/proc','--dev','/dev',
        '--tmpfs','/dev/shm','--tmpfs','/tmp','--dir','/home/bench',
        '--ro-bind','/etc/passwd','/etc/passwd','--ro-bind','/etc/group','/etc/group',
        '--ro-bind','/etc/hosts','/etc/hosts','--ro-bind','/etc/ld.so.cache','/etc/ld.so.cache',
        '--bind',str(work),'/work','--bind',str(build),'/build',
        *git_dir, '--ro-bind',str(helpers),'/bench',
        '--chdir','/work','--clearenv','--setenv','PATH','/usr/bin:/bin',
        '--setenv','HOME','/home/bench','--setenv','LANG','C.UTF-8',
        '--setenv','GIT_OPTIONAL_LOCKS','0','--setenv','GIT_CONFIG_NOSYSTEM','1','--setenv','GIT_CONFIG_GLOBAL','/dev/null',
        '/bin/bash','--noprofile','--norc','-c','umask 077; ulimit -c 0; '+command,
    ]
