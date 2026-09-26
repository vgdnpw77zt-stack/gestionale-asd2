from pathlib import Path
import re
p=Path('/data/top2_app/asd_app/routes_bodymind_fix49.py')
s=p.read_text(encoding='utf-8',errors='replace')
lines=s.splitlines()
for a,b in [(55,80)]:
    print('[upload-probe] '+ ' || '.join(f'{i}:{re.sub(r"\\s+"," ",lines[i-1].strip())[:500]}' for i in range(a,min(b,len(lines))+1)), flush=True)
for m in re.finditer(r'fetch\([^\n]{0,900}',s):
    print('[upload-probe-fetch] '+re.sub(r'\s+',' ',m.group(0))[:1200],flush=True)
