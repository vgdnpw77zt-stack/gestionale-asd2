from pathlib import Path
APP=Path('/data/top2_app')
TARGETS={
 'asd_app/routes_documenti.py':[(331,540),(780,1015),(1016,1105)],
 'asd_app/core.py':[(1588,1620)],
 'asd_app/routes_a159_total_audit_fix.py':[(180,292)],
}
for rel,ranges in TARGETS.items():
    p=APP/rel
    if not p.exists():
        print('[docux3] missing '+rel,flush=True); continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    for a,b in ranges:
        print('[docux3] '+rel+' '+str(a)+'-'+str(b),flush=True)
        for n in range(a,min(b,len(lines))+1):
            print('[docux3] '+rel+':'+str(n)+':'+lines[n-1],flush=True)
