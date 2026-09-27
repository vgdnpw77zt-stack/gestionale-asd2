from pathlib import Path
APP=Path('/data/top2_app')
print('[unified-probe] BEGIN',flush=True)
for rel in ['asd_app/onboarding_flow.py','asd_app/core.py','asd_app/routes_rc2_document_workflow.py','asd_app/routes_goldmaster_ux.py']:
    p=APP/rel
    if not p.exists():
        continue
    txt=p.read_text(encoding='utf-8',errors='replace'); lines=txt.splitlines()
    hits=[]
    for i,line in enumerate(lines,1):
        low=line.lower()
        if any(k in low for k in ('privacy','consenso','liberatoria','manleva','modulo unico','mu-2026','required','obbligatori','document_type')):
            hits.append(i)
    if hits:
        print('[unified-probe] FILE '+rel+' lines='+str(len(lines)),flush=True)
        emitted=set()
        for i in hits[:80]:
            a=max(1,i-5); b=min(len(lines),i+10)
            if any(a<=x<=b for x in emitted): continue
            for n in range(a,b+1):
                print(f'[unified-probe] {rel}:{n}:{lines[n-1][:1400]}',flush=True)
                emitted.add(n)
print('[unified-probe] END',flush=True)
