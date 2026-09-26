from pathlib import Path
APP=Path('/data/top2_app')
TARGETS={
 'asd_app/routes_documenti.py':[(1,430),(840,1100)],
 'asd_app/routes_a159_total_audit_fix.py':[(220,310)],
 'asd_app/routes_goldmaster_final.py':[(90,165)],
}
for rel,ranges in TARGETS.items():
    p=APP/rel
    if not p.exists():
        print('[docux2] missing '+rel,flush=True)
        continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    for a,b in ranges:
        print('[docux2] '+rel+' '+str(a)+'-'+str(b),flush=True)
        for n in range(a,min(b,len(lines))+1):
            line=lines[n-1]
            if rel.endswith('routes_documenti.py') and a==1:
                low=line.lower()
                if not any(k in low for k in ('@app.route','@app.post','send_file','file documento','documento non trovato','filename','documenti/delete','documenti/')):
                    continue
            print('[docux2] '+rel+':'+str(n)+':'+line,flush=True)
