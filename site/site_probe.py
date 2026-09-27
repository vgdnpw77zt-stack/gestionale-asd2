import json,hashlib
from pathlib import Path
DATA=Path('/data')
content=DATA/'site_content.json'
uploads=DATA/'uploads'
print('[site-probe] BEGIN',flush=True)
try:
    c=json.loads(content.read_text(encoding='utf-8')) if content.exists() else {}
except Exception as e:
    print('[site-probe] content-error',repr(e),flush=True); c={}
print('[site-probe] visuals',json.dumps(c.get('visuals',{}),ensure_ascii=False),flush=True)
print('[site-probe] hero',json.dumps(c.get('hero',{}),ensure_ascii=False),flush=True)
refs=set()
def walk(v):
    if isinstance(v,dict):
        for x in v.values(): walk(x)
    elif isinstance(v,list):
        for x in v: walk(x)
    elif isinstance(v,str) and v.startswith('/site-media/'):
        refs.add(v.rsplit('/',1)[-1])
walk(c)
print('[site-probe] referenced',sorted(refs),flush=True)
if uploads.exists():
    for p in sorted(uploads.iterdir()):
        if p.is_file():
            h=hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            print(f'[site-probe] upload name={p.name} size={p.stat().st_size} sha={h} referenced={p.name in refs}',flush=True)
print('[site-probe] END',flush=True)
