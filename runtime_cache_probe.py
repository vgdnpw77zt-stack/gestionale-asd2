from pathlib import Path
import re, json
APP=Path('/data/top2_app')
print('[cache-probe] BEGIN',flush=True)
patterns=[
    'serviceWorker','service-worker','service_worker','sw.js','caches.open','Cache-Control',
    'manifest.webmanifest','manifest.json','navigator.serviceWorker','no-store','max-age',
    'pwa','workbox','stale-while-revalidate','cache-first','network-first'
]
hits=[]
for p in sorted(APP.rglob('*')):
    if not p.is_file(): continue
    if p.suffix.lower() not in {'.py','.js','.html','.json','.css','.txt'} and p.name not in {'sw.js','service-worker.js'}: continue
    try: txt=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    low=txt.lower()
    if any(x.lower() in low for x in patterns):
        rel=str(p.relative_to(APP))
        lines=txt.splitlines()
        print('[cache-probe] FILE '+rel,flush=True)
        emitted=0
        for i,line in enumerate(lines,1):
            ll=line.lower()
            if any(x.lower() in ll for x in patterns):
                a=max(1,i-3);b=min(len(lines),i+6)
                print(f'[cache-probe] CHUNK {rel}:{a}-{b}',flush=True)
                for n in range(a,b+1):
                    print(f'[cache-probe] {n}: {lines[n-1][:900]}',flush=True)
                emitted+=1
                if emitted>=30: break
# Static worker-like files
for p in sorted(APP.rglob('*')):
    if p.is_file() and any(k in p.name.lower() for k in ('service','worker','manifest','sw')):
        print('[cache-probe] CANDIDATE '+str(p.relative_to(APP))+' size='+str(p.stat().st_size),flush=True)
print('[cache-probe] END',flush=True)
