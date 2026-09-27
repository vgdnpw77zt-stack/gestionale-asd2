from pathlib import Path
APP=Path('/data/top2_app')
print('[cache2] BEGIN',flush=True)
for p in sorted(APP.rglob('*')):
    if not p.is_file(): continue
    try: txt=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    low=txt.lower()
    if ('core_assets' in low or 'service-worker.js' in low or 'navigator.serviceworker.register' in low or "cache-control" in low or "caches.open" in low):
        rel=str(p.relative_to(APP))
        print('[cache2] FILE '+rel+' size='+str(len(txt)),flush=True)
        if len(txt)<=25000:
            for i,line in enumerate(txt.splitlines(),1):
                print(f'[cache2] {rel}:{i}:{line[:1200]}',flush=True)
        else:
            for i,line in enumerate(txt.splitlines(),1):
                ll=line.lower()
                if any(k in ll for k in ('core_assets','service-worker.js','navigator.serviceworker.register','cache-control','caches.open','fetch','skipwaiting','clients.claim','max-age','no-store')):
                    a=max(1,i-5);b=min(len(txt.splitlines()),i+10)
                    lines=txt.splitlines()
                    print(f'[cache2] CHUNK {rel}:{a}-{b}',flush=True)
                    for n in range(a,b+1):
                        print(f'[cache2] {rel}:{n}:{lines[n-1][:1200]}',flush=True)
print('[cache2] END',flush=True)
