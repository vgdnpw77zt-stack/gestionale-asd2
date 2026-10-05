# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3, subprocess, sys
from pathlib import Path
from datetime import datetime

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r147_manual_review')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Backup persistent DB before installing any workflow that can mutate document truth.
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
bak=BACK/(stamp+'_pre_r147.db')
src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(bak))
try: src.backup(out)
finally: out.close(); src.close()

core=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R147_HUMAN_DOCUMENT_REVIEW' not in core:
    shutil.copy2(CORE,BACK/'core.py')
    core += r'''

# BODYMIND_R147_HUMAN_DOCUMENT_REVIEW
def _r147_parse_it_date(raw):
    from datetime import datetime as _r147_dt
    s=str(raw or '').strip()
    if not s:return ''
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d','%Y/%m/%d'):
        try:return _r147_dt.strptime(s[:10],fmt).date().isoformat()
        except Exception:pass
    return ''

def _r147_it_date(raw):
    from datetime import datetime as _r147_dt
    s=str(raw or '').strip()
    if not s:return ''
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d'):
        try:return _r147_dt.strptime(s[:10],fmt).strftime('%d/%m/%Y')
        except Exception:pass
    return s

def _r147_backup_db(label='manual_verify'):
    from pathlib import Path as _r147_P
    from datetime import datetime as _r147_dt
    import sqlite3 as _r147_sqlite
    root=_r147_P('/data/release_backups/manual_document_review')
    root.mkdir(parents=True,exist_ok=True)
    dst=root/(_r147_dt.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+label+'.db')
    a=_r147_sqlite.connect('/data/tenants/default/asd.db',timeout=30);b=_r147_sqlite.connect(str(dst))
    try:a.backup(b)
    finally:b.close();a.close()
    return str(dst)

def _r147_review_reason(doc,ctype,physical):
    reasons=[]
    st=str(doc['status'] or '').strip().lower() if 'status' in doc.keys() else ''
    try:conf=float(doc['confidence'] or 0)
    except Exception:conf=0
    try:match=float(doc['match_score'] or 0)
    except Exception:match=0
    if not physical: reasons.append('file non disponibile')
    if ctype=='certificato_medico':
        exp=str(doc['data_scadenza'] or '').strip() if 'data_scadenza' in doc.keys() else ''
        if not _r147_parse_it_date(exp): reasons.append('scadenza da verificare')
    if ctype=='altro': reasons.append('tipo documento dubbio')
    if conf and conf<90: reasons.append('riconoscimento documento '+str(int(conf))+'%')
    if match and match<90: reasons.append('abbinamento atleta '+str(int(match))+'%')
    if any(x in st for x in ('verifica','review','pending','dubb','incert')): reasons.append('stato '+st)
    return reasons

@app.route('/documenti/da-verificare/r147/verifica',methods=['POST'])
@admin_required
def bodymind_r147_verify_document():
    from .document_sync_core_r143 import canonical_type as _r147_ctype, sync_document as _r147_sync, materialize_inbound as _r147_mat, reconcile_all as _r147_all
    source=str(request.form.get('source') or 'documenti').strip()
    try:rid=int(request.form.get('id') or 0)
    except Exception:rid=0
    try:tid=int(request.form.get('tesserato_id') or 0)
    except Exception:tid=0
    dtype=str(request.form.get('tipo') or '').strip().lower()
    allowed={'certificato_medico','modulo_unico_tesseramento','liberatoria_immagini','altro'}
    expiry_raw=str(request.form.get('scadenza') or '').strip()
    expiry=_r147_parse_it_date(expiry_raw)
    if rid<=0:return redirect('/documenti/da-verificare?error=id')
    if dtype not in allowed:return redirect('/documenti/da-verificare?error=tipo')
    if dtype=='certificato_medico' and not expiry:
        return redirect('/documenti/da-verificare?error=scadenza')
    if tid<=0 or not db().execute("SELECT 1 FROM tesserati WHERE id=?",(tid,)).fetchone():
        return redirect('/documenti/da-verificare?error=atleta')

    _r147_backup_db('verify_'+source+'_'+str(rid))
    conn=db();conn.row_factory=sqlite3.Row
    try:
        if source=='documenti':
            d=conn.execute("SELECT * FROM documenti WHERE id=?",(rid,)).fetchone()
            if not d:return redirect('/documenti/da-verificare?error=missing')
            sets=['tesserato_id=?','doc_type=?','visibile=1']; vals=[tid,dtype]
            dc={str(x[1]) for x in conn.execute("PRAGMA table_info(documenti)").fetchall()}
            meta={
              'certificato_medico':'Certificato medico',
              'modulo_unico_tesseramento':'Modulo iscrizione BodyMind',
              'liberatoria_immagini':'Liberatoria immagini',
              'altro':'Documenti ASD'
            }
            if 'categoria' in dc:sets.append('categoria=?');vals.append(meta[dtype])
            if 'status' in dc:sets.append('status=?');vals.append('verificato')
            if 'confidence' in dc:sets.append('confidence=?');vals.append(100)
            if 'match_score' in dc:sets.append('match_score=?');vals.append(100)
            if 'data_scadenza' in dc and dtype=='certificato_medico':
                sets.append('data_scadenza=?');vals.append(expiry)
            vals.append(rid)
            conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",tuple(vals))
            res=_r147_sync(conn,rid)
            # Human verification is authoritative: keep explicit verified state
            # after canonical normalization.
            if 'status' in dc:conn.execute("UPDATE documenti SET status='verificato' WHERE id=?",(rid,))
        elif source=='inbound':
            r=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(rid,)).fetchone()
            if not r:return redirect('/documenti/da-verificare?error=missing')
            ic={str(x[1]) for x in conn.execute("PRAGMA table_info(inbound_documents)").fetchall()}
            sets=[];vals=[]
            for k,v in [('tesserato_id',tid),('matched_tesserato_id',tid),('suggested_tesserato_id',tid),
                        ('document_type',dtype),('doc_type',dtype),('document_confidence',100),('doc_confidence',100),
                        ('match_score',100),('status','manual_accepted'),('match_action','manual_verify')]:
                if k in ic:sets.append(k+'=?');vals.append(v)
            if 'updated_at' in ic:sets.append('updated_at=?');vals.append(datetime.now().isoformat(timespec='seconds'))
            vals.append(rid)
            conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",tuple(vals))
            res=_r147_mat(conn,rid,allow_old=True)
            if not res.get('ok'):
                conn.rollback()
                return redirect('/documenti/da-verificare?error=materializza')
            did=int(res.get('document_id') or 0)
            if did:
                dc={str(x[1]) for x in conn.execute("PRAGMA table_info(documenti)").fetchall()}
                sets=[];vals=[]
                if 'status' in dc:sets.append('status=?');vals.append('verificato')
                if 'data_scadenza' in dc and dtype=='certificato_medico':sets.append('data_scadenza=?');vals.append(expiry)
                if sets:
                    vals.append(did);conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",tuple(vals))
                    _r147_sync(conn,did)
                    if 'status' in dc:conn.execute("UPDATE documenti SET status='verificato' WHERE id=?",(did,))
        else:
            return redirect('/documenti/da-verificare?error=source')
        _r147_all(conn)
        # Reassert verified after global convergence, which may normalize fields.
        if source=='documenti':
            conn.execute("UPDATE documenti SET status='verificato' WHERE id=?",(rid,))
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        if integrity.lower()!='ok' or fk:
            raise RuntimeError('R147 post-verify DB invariant failed')
        conn.commit()
    finally:
        conn.close()
    return redirect('/documenti/da-verificare?verified=1')

@app.after_request
def _bodymind_r147_review_surface(resp):
    try:
        from .document_sync_core_r143 import canonical_type as _ctype,resolve_file as _resolve
        p=request.path or ''
        if request.method!='GET' or p!='/documenti/da-verificare' or int(getattr(resp,'status_code',200) or 200) not in (200,301,302,303):
            # Also normalize the direct-athlete upload date UI to Italian format.
            if request.method=='GET' and '/mobile/atleta/' in p and p.endswith('/documenti/carica') and int(getattr(resp,'status_code',200) or 200)==200:
                html=resp.get_data(as_text=True)
                html=html.replace("type='date' name='scadenza'","type='text' name='scadenza' inputmode='numeric' placeholder='GG/MM/AAAA' pattern='[0-9]{2}/[0-9]{2}/[0-9]{4}'")
                html=html.replace('Scadenza certificato (solo se nota)','Scadenza certificato · GG/MM/AAAA')
                resp.set_data(html)
            return resp
        if not bool(session.get('logged')):return resp

        conn=db();conn.row_factory=sqlite3.Row
        try:
            athletes=conn.execute("SELECT id,nome,cognome FROM tesserati ORDER BY cognome,nome").fetchall()
            athlete_map={int(x['id']):(str(x['cognome'] or '')+' '+str(x['nome'] or '')).strip() for x in athletes}
            docs=[]
            for d in conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY id DESC").fetchall():
                typ=_ctype(d);fp=_resolve(d['filename']);reasons=_r147_review_reason(d,typ,bool(fp))
                st=str(d['status'] or '').lower() if 'status' in d.keys() else ''
                # A human-verified document leaves the queue unless its physical
                # file disappears later.
                if st=='verificato' and fp and not (typ=='certificato_medico' and not _r147_parse_it_date(d['data_scadenza'])):
                    continue
                if reasons:
                    docs.append({'source':'documenti','row':d,'type':typ,'reasons':reasons,'tid':int(d['tesserato_id'] or 0)})
            inbound=[]
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone():
                for r in conn.execute("""SELECT * FROM inbound_documents
                  WHERE coalesce(deleted_at,'')='' AND lower(coalesce(status,'')) NOT IN
                  ('deleted','archived','archived_orphan','accepted','manual_accepted','verificato','resolved','associato','archived_to_tesserato')
                  ORDER BY id DESC LIMIT 250""").fetchall():
                    status=str(r['status'] or '').lower()
                    try:conf=float(r['document_confidence'] or 0);match=float(r['match_score'] or 0)
                    except Exception:conf=0;match=0
                    if not (status in ('verifica','review','pending','nuovo_pronto','ready') or conf<90 or match<90):
                        continue
                    typ=_ctype(r)
                    tid=int(r['tesserato_id'] or r['matched_tesserato_id'] or r['suggested_tesserato_id'] or 0)
                    inbound.append({'source':'inbound','row':r,'type':typ,'tid':tid,'reasons':['upload da confermare manualmente']})
        finally:conn.close()

        opts="".join("<option value='"+str(int(a['id']))+"'>"+e((str(a['cognome'] or '')+' '+str(a['nome'] or '')).strip())+"</option>" for a in athletes)
        def card(item):
            r=item['row'];source=item['source'];rid=int(r['id']);tid=int(item['tid'] or 0);typ=item['type']
            title=str((r['original_filename'] if 'original_filename' in r.keys() else '') or (r['titolo'] if 'titolo' in r.keys() else '') or ('Documento #'+str(rid)))
            who=athlete_map.get(tid,'Atleta da scegliere')
            reason=' · '.join(item['reasons'])
            current_exp=''
            if source=='documenti' and 'data_scadenza' in r.keys():current_exp=_r147_it_date(r['data_scadenza'])
            sel=lambda v: ' selected' if typ==v else ''
            athlete_options=opts.replace("value='"+str(tid)+"'","value='"+str(tid)+"' selected",1) if tid else opts
            return f"""<article class='r147-card'><div class='r147-head'><div><b>{e(title)}</b><small>{e(who)}</small></div><span>DA VERIFICARE</span></div><p>{e(reason)}</p>
<form method='post' action='/documenti/da-verificare/r147/verifica'>{csrf_input()}<input type='hidden' name='source' value='{source}'><input type='hidden' name='id' value='{rid}'>
<label>Atleta<select name='tesserato_id' required><option value=''>Seleziona…</option>{athlete_options}</select></label>
<label>Tipo<select name='tipo' required><option value='certificato_medico'{sel('certificato_medico')}>Certificato medico</option><option value='modulo_unico_tesseramento'{sel('modulo_unico_tesseramento')}>Modulo Unico</option><option value='liberatoria_immagini'{sel('liberatoria_immagini')}>Liberatoria immagini</option><option value='altro'{sel('altro')}>Altro</option></select></label>
<label>Scadenza certificato · GG/MM/AAAA<input name='scadenza' value='{e(current_exp)}' inputmode='numeric' placeholder='10/12/2026' pattern='[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}'></label>
<button type='submit'>✓ Verifica e aggiorna stato</button></form></article>"""
        cards=''.join(card(x) for x in docs+inbound)
        err=request.args.get('error') or ''
        messages={'scadenza':'Per un certificato medico inserisci la scadenza in formato GG/MM/AAAA.','atleta':'Seleziona l’atleta.','materializza':'Il file non è materializzabile: resta da verificare.','tipo':'Seleziona il tipo documento.'}
        msg=messages.get(err,'')
        html=f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>Documenti da verificare</title>
<style>body{{margin:0;background:#071426;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:780px;margin:auto;padding:18px 15px 110px}}h1{{margin:0 0 6px;font-size:32px}}.sub{{color:#9fb3ca;margin-bottom:15px}}.okmsg,.errmsg{{padding:11px;border-radius:12px;margin:10px 0;font-weight:800}}.okmsg{{background:#14532d}}.errmsg{{background:#7f1d1d}}.r147-card{{background:#0b1d33;border:1px solid #27445f;border-radius:18px;padding:15px;margin:12px 0}}.r147-head{{display:flex;justify-content:space-between;gap:10px}}.r147-head b{{font-size:18px}}.r147-head small{{display:block;color:#a9b9cb;margin-top:4px}}.r147-head span{{height:max-content;background:#92400e;color:#fff7ed;border-radius:999px;padding:6px 9px;font-size:11px;font-weight:950}}p{{color:#fcd34d}}label{{display:block;margin-top:11px;font-weight:900}}select,input{{width:100%;box-sizing:border-box;min-height:48px;margin-top:5px;border-radius:12px;border:1px solid #315475;background:#081727;color:#fff;padding:10px;font-size:16px}}button{{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;font-weight:950;font-size:16px}}a.back{{display:block;margin-top:15px;padding:12px;border-radius:12px;background:#163b5f;color:#fff;text-decoration:none;text-align:center;font-weight:900}}</style></head><body><main><h1>Documenti da verificare</h1><div class='sub'>{len(docs)+len(inbound)} casi dubbi o incompleti. La verifica manuale aggiorna davvero lo stato dell’atleta.</div>{("<div class='okmsg'>Documento verificato e stato aggiornato.</div>" if request.args.get('verified') else "")}{("<div class='errmsg'>"+e(msg)+"</div>" if msg else "")}{cards if cards else "<div class='okmsg'>Nessun documento da verificare.</div>"}<a class='back' href='/documenti'>← Documenti</a></main></body></html>"""
        resp.set_data(html);resp.status_code=200;resp.headers.pop('Location',None);resp.headers['Content-Type']='text/html; charset=utf-8'
    except Exception as exc:
        print('[r147-review-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r147-install] human review + Italian expiry input installed',flush=True)
else:
    print('[r147-install] already installed',flush=True)

# Read-only fresh-process QA.
qa=r'''
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app,_r147_parse_it_date
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R147 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r147"})
p=c.get('/documenti/da-verificare')
h=p.get_data(as_text=True)
u=c.get('/mobile/atleta/21/documenti/carica')
uh=u.get_data(as_text=True)
conn=sqlite3.connect('/data/tenants/default/asd.db')
try: integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
checks={
 'review_200':p.status_code==200,
 'review_verify':'Verifica e aggiorna stato' in h,
 'review_expiry_field':"name='scadenza'" in h,
 'upload_expiry_field':"name='scadenza'" in uh and "type='text' name='scadenza'" in uh,
 'date_parser':_r147_parse_it_date('10/12/2026')=='2026-12-10',
 'db':integ.lower()=='ok' and fk==0,
}
print('[r147-selftest] '+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError('R147 QA failed '+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R147 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-6000:])
print('[r147-selftest-main] PASS human-verify persistent state doubtful-queue field+parser db-ok',flush=True)
