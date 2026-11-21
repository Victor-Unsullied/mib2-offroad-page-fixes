import hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def integrity():
 manifest=json.loads((ROOT/'MANIFEST.json').read_text())
 if manifest.get('self_contained') is not True:raise ValueError('Standalone manifest missing')
 seen=set()
 for row in manifest['files']:
  name=row['path'];path=(ROOT/name).resolve()
  if name in seen or not path.is_relative_to(ROOT) or not path.is_file():raise ValueError('Missing/external package file: '+name)
  seen.add(name);data=path.read_bytes()
  if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Package file changed: '+name)
  if path.suffix=='.jar':
   with zipfile.ZipFile(path) as z:
    if z.testzip() is not None:raise ValueError('Damaged JAR: '+name)
 if not {'install.py','RUNBOOK.txt'}<=seen:raise ValueError('Incomplete package')
 return len(seen)
def invoke(name,args):
 path=(ROOT/'lib'/name).resolve()
 if not path.is_relative_to(ROOT):raise ValueError('External controller')
 bootstrap="import runpy,sys;from pathlib import Path;p=Path(sys.argv[1]).resolve();sys.path.insert(0,str(p.parent));sys.argv=sys.argv[1:];runpy.run_path(str(p),run_name='__main__')"
 subprocess.run([sys.executable,'-I','-B','-c',bootstrap,str(path),*args],cwd=ROOT,check=True)
