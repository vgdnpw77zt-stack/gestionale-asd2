from pathlib import Path
import re
p=Path('/data/top2_app/asd_app/routes_bodymind_fix49.py')
s=p.read_text(encoding='utf-8',errors='replace')
lines=s.splitlines()
def clean(v):
    return re.sub(r'\\s+',' ',v.strip())[:500]
for a,b in [(55,80)]:
    out=[]
    for i in range(a,min(b,len(lines))+1):
        out.append(str(i)+':'+clean(lines[i-1]))
    print('[upload-probe] '+' || '.join(out), flush=True)
for m in re.finditer(r'fetch\\([^\\n]{0,1200}',s):
    print('[upload-probe-fetch] '+clean(m.group(0))[:1200],flush=True)
