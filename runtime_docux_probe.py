from pathlib import Path
import re
APP=Path('/data/top2_app')
TERMS=('File documento non trovato sul disco','Vista unica compatta','Archivio operativo','Elenco documenti del tesserato','Caricamento manuale','Copia o compila','Collega')
print('[docux-probe] begin', flush=True)
for p in APP.rglob('*.py'):
    try:
        lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    except Exception:
        continue
    hits=[]
    for i,line in enumerate(lines,1):
        if any(t.lower() in line.lower() for t in TERMS):
            hits.append(i)
    if not hits:
        continue
    rel=str(p.relative_to(APP))
    print('[docux-probe] file='+rel, flush=True)
    for i in hits:
        a=max(1,i-6); b=min(len(lines),i+12)
        for n in range(a,b+1):
            print('[docux-probe] '+rel+':'+str(n)+':'+re.sub(r'\s+',' ',lines[n-1].strip())[:450], flush=True)
print('[docux-probe] end', flush=True)
