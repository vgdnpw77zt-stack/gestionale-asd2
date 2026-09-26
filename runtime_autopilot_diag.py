from pathlib import Path
import re, hashlib
APP=Path('/data/top2_app')
FILES=['asd_app/routes_bodymind_fix49.py','asd_app/routes_inbound_documents.py','asd_app/routes_email_documents.py','asd_app/core.py']
TERMS=['/autopilot/upload','fetch(','AbortController','setTimeout','FormData','preventDefault','type="file"',"type='file'",'<form','addEventListener','onsubmit','onclick']
def clean(line):
    return re.sub(r'\s+',' ',line.strip())[:360]
print('[upload-diag] begin', flush=True)
for rel in FILES:
    p=APP/rel
    if not p.exists():
        print(f'[upload-diag] missing {rel}', flush=True); continue
    s=p.read_text(encoding='utf-8',errors='replace')
    print(f'[upload-diag] file={rel} sha256={hashlib.sha256(s.encode()).hexdigest()[:16]} lines={len(s.splitlines())}', flush=True)
    lines=s.splitlines()
    hit_lines=set()
    for i,line in enumerate(lines,1):
        if any(t.lower() in line.lower() for t in TERMS):
            for j in range(max(1,i-8),min(len(lines),i+12)+1):
                hit_lines.add(j)
    if hit_lines:
        groups=[]; cur=[]; last=None
        for n in sorted(hit_lines):
            if last is None or n==last+1:
                cur.append(n)
            else:
                groups.append(cur); cur=[n]
            last=n
        if cur: groups.append(cur)
        for g in groups[:18]:
            chunk=' || '.join(str(n)+':'+clean(lines[n-1]) for n in g)
            print(f'[upload-diag] {rel} range {g[0]}-{g[-1]}: {chunk}', flush=True)
print('[upload-diag] end', flush=True)
