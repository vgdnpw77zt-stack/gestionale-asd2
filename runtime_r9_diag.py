from pathlib import Path
APP=Path('/data/top2_app')
for rel,ranges in {
 'asd_app/routes_inbound_documents.py':[(205,285),(335,390)],
 'asd_app/routes_tesserati.py':[(145,180),(190,260)],
}.items():
 p=APP/rel
 if not p.exists():
  print('[r9diag] missing '+rel,flush=True); continue
 lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
 for a,b in ranges:
  print('[r9diag] '+rel+' '+str(a)+'-'+str(b),flush=True)
  for n in range(a,min(b,len(lines))+1):
   print('[r9diag] '+str(n)+':'+lines[n-1],flush=True)
