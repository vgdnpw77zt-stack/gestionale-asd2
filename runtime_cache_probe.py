from pathlib import Path
APP=Path('/data/top2_app')
print('[cache3] BEGIN',flush=True)
targets=[
    APP/'static/pwa/service-worker.js',
    APP/'static/pwa/sw.js',
    APP/'asd_app/routes_iscrizione_online.py',
    APP/'asd_app/routes_release_20260926.py',
    APP/'asd_app/routes_a146_commercial_qa.py',
]
for p in targets:
    if not p.exists():
        print('[cache3] MISSING '+str(p.relative_to(APP)),flush=True); continue
    txt=p.read_text(encoding='utf-8',errors='replace')
    lines=txt.splitlines(); rel=str(p.relative_to(APP))
    print('[cache3] FILE '+rel+' lines='+str(len(lines)),flush=True)
    if p.name in ('service-worker.js','sw.js') or len(lines)<120:
        ranges=[(1,len(lines))]
    else:
        ranges=[]
        for i,line in enumerate(lines,1):
            low=line.lower()
            if 'service-worker.js' in low or 'static/pwa/sw.js' in low or 'cache-control' in low or 'after_request' in low or 'serviceworker.register' in low:
                ranges.append((max(1,i-12),min(len(lines),i+22)))
    seen=set()
    for a,b in ranges:
        if (a,b) in seen: continue
        seen.add((a,b))
        print(f'[cache3] RANGE {rel}:{a}-{b}',flush=True)
        for n in range(a,b+1):
            print(f'[cache3] {rel}:{n}:{lines[n-1][:1400]}',flush=True)
print('[cache3] END',flush=True)
