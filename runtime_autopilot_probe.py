from pathlib import Path
import re, hashlib
APP=Path('/data/top2_app')
print('[r7-probe] begin', flush=True)
for rel in ['asd_app/routes_bodymind_fix49.py','asd_app/core.py','asd_app/routes_pwa.py']:
    p=APP/rel
    if not p.exists():
        continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    hits=[]
    for i,line in enumerate(lines):
        low=line.lower()
        if any(k in low for k in ['/autopilot/upload','fetch(','xmlhttprequest','preventdefault','addEventListener'.lower(),'service-worker','formdata','type="file"',"type='file'"]):
            a=max(0,i-3); b=min(len(lines),i+6)
            chunk=' || '.join(f'{j+1}:{re.sub(r"\\s+"," ",lines[j].strip())[:420]}' for j in range(a,b))
            hits.append(chunk)
    print(f'[r7-probe] {rel} sha256={hashlib.sha256(p.read_bytes()).hexdigest()[:16]}',flush=True)
    for h in hits[:40]:
        print('[r7-probe] '+h,flush=True)
print('[r7-probe] end', flush=True)
