from pathlib import Path
import sqlite3, json
APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
print('[unified2] BEGIN',flush=True)
ranges={
 'core.py':[(160,195),(1250,1325),(3715,3765),(4245,4280)],
 'routes_minori.py':[(1,35),(50,110)],
 'routes_a151_final_ops.py':[(245,292)],
 'routes_documenti.py':[(875,912)],
 'onboarding_flow.py':[(1,120)],
}
for name,rs in ranges.items():
    p=APP/'asd_app'/name
    if not p.exists(): continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    for a,b in rs:
        print(f'[unified2] SOURCE {name} {a}-{b}',flush=True)
        for n in range(a,min(b,len(lines))+1):
            print(f'[unified2] {name}:{n}:{lines[n-1][:1400]}',flush=True)
if DB.exists():
    c=sqlite3.connect(str(DB)); c.row_factory=sqlite3.Row
    try:
        q="""SELECT i.id,i.tesserato_id,i.status,i.document_type,i.document_confidence,i.match_score,
                    t.minorenne,t.consenso_informato,t.liberatoria_immagini,t.manleva_firmata,
                    t.iscrizione_firmata,t.documenti_onboarding_ok,t.privacy_ok,t.liberatoria_ok,t.regolamento_ok,
                    m.consenso_firmato,m.delega_ritiro_ok,m.uscita_autonoma_ok,m.autorizzazioni_ok
             FROM inbound_documents i
             JOIN tesserati t ON t.id=i.tesserato_id
             LEFT JOIN minori m ON m.tesserato_id=t.id
             WHERE i.document_type='modulo_unico_tesseramento'
             ORDER BY i.id DESC"""
        rows=[dict(r) for r in c.execute(q).fetchall()]
        print('[unified2] MU_LINKED='+json.dumps(rows,ensure_ascii=False),flush=True)
        q2="""SELECT t.id,t.minorenne,t.consenso_informato,t.liberatoria_immagini,t.manleva_firmata,
                    t.iscrizione_firmata,t.documenti_onboarding_ok,t.privacy_ok,t.liberatoria_ok,t.regolamento_ok,
                    m.consenso_firmato,m.delega_ritiro_ok,m.uscita_autonoma_ok,m.autorizzazioni_ok
              FROM tesserati t LEFT JOIN minori m ON m.tesserato_id=t.id
              WHERE COALESCE(t.minorenne,0)=1 OR m.id IS NOT NULL ORDER BY t.id"""
        print('[unified2] MINOR_FLAGS='+json.dumps([dict(r) for r in c.execute(q2).fetchall()],ensure_ascii=False),flush=True)
    finally:c.close()
print('[unified2] END',flush=True)
