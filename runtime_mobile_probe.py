from pathlib import Path
APP=Path('/data/top2_app')
print('[mobile2] BEGIN',flush=True)
for rel,ranges in {
 'asd_app/routes_bodymind_fix22.py':[(1,220)],
 'asd_app/routes_bodymind_fix23.py':[(1,210)],
}.items():
    p=APP/rel
    if not p.exists():
        print('[mobile2] MISSING '+rel,flush=True); continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    print('[mobile2] FILE '+rel+' lines='+str(len(lines)),flush=True)
    for a,b in ranges:
        for n in range(a,min(b,len(lines))+1):
            print(f'[mobile2] {rel}:{n}:{lines[n-1][:1400]}',flush=True)
print('[mobile2] END',flush=True)
