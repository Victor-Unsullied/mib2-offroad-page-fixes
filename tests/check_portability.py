"""Verify a relocated copy while denying network and reads outside the package/Python."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# Each verification child installs the audit hook before loading a controller.
GUARDED_LOADER = r'''
import os,runpy,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
script=Path(sys.argv[2]).resolve()
python_roots={Path(sys.prefix).resolve(),Path(sys.base_prefix).resolve()}
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise RuntimeError('Offline portability check attempted network access')
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=Path(os.fsdecode(args[0])).resolve()
        if not path.is_relative_to(root) and not any(path.is_relative_to(p) for p in python_roots):
            raise RuntimeError('Read outside portable package: '+str(path))
sys.addaudithook(audit)
sys.path.insert(0,str(script.parent))
sys.argv=sys.argv[2:]
runpy.run_path(str(script),run_name='__main__')
'''


def check():
    with tempfile.TemporaryDirectory(prefix='MIB2 portable verification ') as temporary:
        destination = Path(temporary) / 'relocated corrections with spaces'
        shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns('__pycache__', 'live', 'installation', 'state'))
        jobs = [('lib/native_menu.py', ['verify']), ('menu_visibility.py', ['plan'])]
        for name, arguments in jobs:
            result = subprocess.run([sys.executable, '-I', '-B', '-c', GUARDED_LOADER,
                str(destination), str(destination / name), *arguments],
                cwd=temporary, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(name + '\n' + result.stdout + result.stderr)
        # Exercise the real entry point and its separate child interpreters too.
        verified = subprocess.run([sys.executable, '-I', '-B', str(destination / 'menu_visibility.py'), 'verify'],
            cwd=temporary, capture_output=True, text=True, timeout=45)
        if verified.returncode:
            raise RuntimeError(verified.stdout + verified.stderr)
        missing_device_arguments = [(['apply'], '--live'), (['apply', '--live'], '--host')]
        for arguments, expected in missing_device_arguments:
            denied = subprocess.run([sys.executable, '-I', '-B', '-c', GUARDED_LOADER,
                str(destination), str(destination / 'menu_visibility.py'), *arguments],
                cwd=temporary, capture_output=True, text=True, timeout=10)
            if denied.returncode != 2 or expected not in denied.stderr:
                raise RuntimeError('Missing explicit device gate: ' + str(arguments))
        # A damaged payload must fail locally before a live action can dispatch.
        payload = destination / 'MENU.json'
        payload.write_bytes(payload.read_bytes() + b'corrupt-fixture')
        corrupted = subprocess.run([sys.executable, '-I', '-B', str(destination / 'menu_visibility.py'), 'verify'],
            cwd=temporary, capture_output=True, text=True, timeout=15)
        if corrupted.returncode != 1 or 'Package file changed' not in corrupted.stderr:
            raise RuntimeError('Damaged-payload verification did not refuse the package')
    print(json.dumps({'status': 'PASS_RELOCATED_PACKAGE', 'outside_package_reads': 0,
                      'network_attempts': 0, 'guarded_controller_checks': len(jobs),
                      'missing_device_arguments_refused': len(missing_device_arguments), 'damaged_payload_refused': True}))


if __name__ == '__main__':
    check()
