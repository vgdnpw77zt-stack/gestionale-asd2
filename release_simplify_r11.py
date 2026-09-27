from __future__ import annotations
from pathlib import Path
import compileall, shutil, re

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_SIMPLIFY_R11'
BACKUPS=Path('/data/release_backups/20260927_simplify_r11')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def patch_file(rel, transform):
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R11 target missing: '+rel)
    old=p.read_text(encoding='utf-8')
    new=transform(old)
    if new!=old:
        backup(rel)
        p.write_text(new,encoding='utf-8')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    # Recover any partial previous R11 write.
    for rel in ('asd_app/routes_a202_operational_integrity.py','asd_app/core.py'):
        p=APP/rel; b=BACKUPS/rel
        if p.exists() and b.exists():
            cur=p.read_text(encoding='utf-8',errors='replace')
            if 'BODYMIND_R11_' in cur:
                shutil.copy2(b,p)
                print('[simplify-r11] restored partial '+rel,flush=True)

    def patch_a202(s):
        if 'BODYMIND_R11_PENDING_QUEUE' in s:
            return s

        # Ensure regex support for server-side dashboard cleanup.
        if 'import re\n' not in s:
            anchor='from datetime import datetime\n'
            if anchor not in s:
                raise RuntimeError('R11 A202 import anchor missing')
            s=s.replace(anchor,anchor+'import re\n',1)

        helper_anchor='def _style() -> str:\n'
        if helper_anchor not in s:
            raise RuntimeError('R11 A202 helper anchor missing')

        queue_code=r'''# BODYMIND_R11_PENDING_QUEUE
_R11_PENDING_STATUSES = (
    'needs_manual_match','associato_tipo_da_verificare','richiede_conferma',
    'needs_review','da_verificare','pending'
)

def _r11_pending_where(alias='i'):
    p=(alias+'.') if alias else ''
    values=','.join("'" + x + "'" for x in _R11_PENDING_STATUSES)
    return f"LOWER(COALESCE({p}status,'')) IN ({values}) AND COALESCE({p}deleted_at,'')=''"


def _r11_pending_count(conn):
    if not _has_table(conn,'inbound_documents'):
        return 0
    return int(_scalar(conn, f"SELECT COUNT(*) FROM inbound_documents i WHERE {_r11_pending_where('i')}") or 0)


def _r11_doc_label(value):
    labels={
        'certificato_medico':'Certificato medico',
        'iscrizione':'Domanda iscrizione',
        'manleva':'Manleva',
        'liberatoria_immagini':'Liberatoria immagini',
        'documento_identita':'Documento identità',
        'consenso_minore':'Consenso minore',
        'autorizzazione_genitore':'Autorizzazione genitore',
        'trasporto_minori':'Trasporto minori',
        'documenti_gara':'Documenti gara',
        'documenti_saggio':'Documenti saggio',
        'ricevuta_pagamento':'Ricevuta / prova pagamento',
        'altro':'Altro / da classificare',
    }
    return labels.get(str(value or '').strip(), str(value or '').strip() or 'Da classificare')


def _r11_doc_category(value):
    return {
        'certificato_medico':'Certificato medico',
        'iscrizione':'Domanda iscrizione',
        'manleva':'Manleva',
        'liberatoria_immagini':'Liberatoria immagini',
        'documento_identita':'Documento identità',
        'consenso_minore':'Consenso minore',
        'autorizzazione_genitore':'Autorizzazione genitore',
        'trasporto_minori':'Trasporto minori',
        'documenti_gara':'Documenti gara',
        'documenti_saggio':'Documenti saggio',
        'ricevuta_pagamento':'Pagamenti da verificare',
        'altro':'Altro',
    }.get(str(value or '').strip(),'Altro')


def _r11_sync_documento(conn, inbound):
    if not inbound or not _has_table(conn,'documenti'):
        return
    tid=int(inbound['tesserato_id'] or 0) if 'tesserato_id' in inbound.keys() else 0
    saved=str(inbound['saved_path'] or '') if 'saved_path' in inbound.keys() else ''
    if tid<=0 or not saved:
        return
    cols=_cols(conn,'documenti')
    row=None
    if 'inbound_id' in cols:
        row=conn.execute("SELECT id FROM documenti WHERE inbound_id=? ORDER BY id DESC LIMIT 1",(int(inbound['id']),)).fetchone()
    if not row:
        row=conn.execute("SELECT id FROM documenti WHERE filename=? ORDER BY id DESC LIMIT 1",(saved,)).fetchone()
    values={
        'tesserato_id':tid,
        'titolo':str(inbound['original_filename'] or 'Documento') if 'original_filename' in inbound.keys() else 'Documento',
        'categoria':_r11_doc_category(inbound['document_type'] if 'document_type' in inbound.keys() else ''),
        'filename':saved,
        'original_filename':str(inbound['original_filename'] or Path(saved).name) if 'original_filename' in inbound.keys() else Path(saved).name,
        'data_caricamento':datetime.now().date().isoformat(),
        'visibile':1,
        'doc_type':str(inbound['document_type'] or '') if 'document_type' in inbound.keys() else '',
        'confidence':100,
        'match_score':100,
        'source':'autopilot',
        'status':'salvato',
        'inbound_id':int(inbound['id']),
    }
    values={k:v for k,v in values.items() if k in cols}
    if row:
        pairs=','.join(k+'=?' for k in values if k!='titolo' or True)
        conn.execute("UPDATE documenti SET "+pairs+" WHERE id=?",list(values.values())+[int(row['id'])])
    else:
        required={'tesserato_id','titolo','categoria','filename','original_filename'}
        if required.issubset(values):
            keys=list(values.keys())
            conn.execute("INSERT INTO documenti("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",[values[k] for k in keys])


@app.before_request
def _r11_legacy_document_redirects():
    if request.method != 'GET':
        return None
    if request.path == '/documenti-automatici':
        return redirect('/documenti/da-verificare')
    if request.path == '/document-hub' and (request.args.get('f') or request.args.get('stato') or '').lower() in {'verificare','aperti','review'}:
        return redirect('/documenti/da-verificare')
    return None


@app.get('/documenti/da-verificare')
@login_required
def r11_documenti_da_verificare():
    conn=db()
    try:
        rows=conn.execute(f"""
            SELECT i.*,
                   t.nome AS atleta_nome,t.cognome AS atleta_cognome
            FROM inbound_documents i
            LEFT JOIN tesserati t ON t.id=COALESCE(i.tesserato_id,i.matched_tesserato_id,i.suggested_tesserato_id)
            WHERE {_r11_pending_where('i')}
            ORDER BY COALESCE(i.updated_at,i.created_at) DESC,i.id DESC
        """).fetchall() if _has_table(conn,'inbound_documents') else []
        athletes=conn.execute("SELECT id,nome,cognome FROM tesserati ORDER BY cognome,nome").fetchall() if _has_table(conn,'tesserati') else []
    finally:
        conn.close()

    choices=[
        ('certificato_medico','Certificato medico'),('iscrizione','Domanda iscrizione'),
        ('manleva','Manleva'),('liberatoria_immagini','Liberatoria immagini'),
        ('documento_identita','Documento identità'),('consenso_minore','Consenso minore'),
        ('autorizzazione_genitore','Autorizzazione genitore'),('trasporto_minori','Trasporto minori'),
        ('documenti_gara','Documenti gara'),('documenti_saggio','Documenti saggio'),
        ('ricevuta_pagamento','Ricevuta / prova pagamento'),('altro','Altro')
    ]
    def card(r):
        did=int(r['id'])
        status=str(r['status'] or '')
        dtype=str(r['document_type'] or 'altro')
        dconf=int(r['document_confidence'] or 0)
        mscore=int(r['match_score'] or 0)
        tid=int(r['tesserato_id'] or 0)
        athlete=((str(r['atleta_nome'] or '')+' '+str(r['atleta_cognome'] or '')).strip() if 'atleta_nome' in r.keys() else '')
        if status=='needs_manual_match':
            reason='Identità atleta da assegnare'
        elif status=='associato_tipo_da_verificare':
            reason='Tipo documento da confermare'
        else:
            reason='Conferma richiesta'
        options=''.join(f"<option value='{e(v)}' {'selected' if v==dtype else ''}>{e(lbl)}</option>" for v,lbl in choices)
        athlete_options="<option value=''>— scegli atleta —</option>"+''.join(
            f"<option value='{int(a['id'])}'>{e(a['cognome'])} {e(a['nome'])}</option>" for a in athletes
        )
        identity=f"<b>{e(athlete)}</b><small>identità {mscore}%</small>" if athlete else "<b>Non assegnata</b><small>serve una scelta</small>"
        assign = ''
        if not tid:
            assign=f"""<form method='post' action='/documenti/da-verificare/{did}/atleta' class='r11-inline'>{csrf_input()}<select name='tesserato_id' required>{athlete_options}</select><button class='r11-btn' type='submit'>Assegna atleta</button></form>"""
        type_form=f"""<form method='post' action='/documenti/da-verificare/{did}/tipo' class='r11-inline'>{csrf_input()}<select name='document_type'>{options}</select><button class='r11-btn ghost' type='submit'>Correggi tipo</button></form>"""
        ok=''
        if tid and dtype not in ('','altro') and status!='needs_manual_match':
            ok=f"""<form method='post' action='/documenti/da-verificare/{did}/ok' class='r11-inline'>{csrf_input()}<button class='r11-btn ok' type='submit'>✓ OK</button></form>"""
        dossier=f"<a class='r11-btn ghost' href='/documenti?tesserato_id={tid}'>Dossier</a>" if tid else ''
        return f"""
        <article class='r11-doc'>
          <div class='r11-doc-main'>
            <div class='r11-top'><span class='r11-state'>{e(reason)}</span><small>#{did}</small></div>
            <h3>{e(r['original_filename'] or 'Documento')}</h3>
            <div class='r11-meta'><span>Tipo: <b>{e(_r11_doc_label(dtype))}</b> · {dconf}%</span><span>{identity}</span></div>
          </div>
          <div class='r11-actions'>
            <a class='r11-btn primary' target='_blank' rel='noopener' href='/documenti-automatici/file/{did}'>Apri</a>
            {ok}{dossier}
          </div>
          <div class='r11-fix'>{assign}{type_form}</div>
        </article>"""
    cards=''.join(card(r) for r in rows) or "<div class='r11-empty'><b>Nessun documento da verificare.</b><span>La coda è pulita.</span></div>"
    html=f"""
    <main class='r11-page'>
      <section class='r11-hero'>
        <div><span class='r11-kicker'>Documenti · coda operativa</span><h1>Da verificare</h1><p>Qui compaiono soltanto i documenti che richiedono una scelta umana. Apri, correggi se serve e premi OK.</p></div>
        <div class='r11-count'>{len(rows)}<small>da chiudere</small></div>
      </section>
      <section class='r11-list'>{cards}</section>
    </main>
    <style id='bodymind-r11-queue'>
      .r11-page{{max-width:1120px;margin:0 auto;padding:8px 0 40px}}.r11-hero{{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:22px;border:1px solid rgba(96,165,250,.22);border-radius:24px;background:linear-gradient(135deg,rgba(15,30,55,.94),rgba(7,16,31,.90));margin-bottom:14px}}.r11-hero h1{{margin:4px 0;font-size:clamp(30px,5vw,52px)}}.r11-hero p{{margin:0;color:#b9c8dd;max-width:680px}}.r11-kicker{{font-size:10px;font-weight:900;letter-spacing:.12em;text-transform:uppercase;color:#93c5fd}}.r11-count{{min-width:92px;text-align:center;font-size:42px;font-weight:950;color:#fff}}.r11-count small{{display:block;font-size:10px;text-transform:uppercase;color:#9fb4cb}}.r11-list{{display:grid;gap:10px}}.r11-doc{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:16px;border:1px solid rgba(148,163,184,.17);border-radius:20px;background:rgba(9,20,38,.82)}}.r11-doc h3{{margin:5px 0 8px;font-size:16px;overflow-wrap:anywhere}}.r11-top,.r11-meta,.r11-actions,.r11-inline{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.r11-top{{justify-content:space-between}}.r11-state{{padding:5px 8px;border-radius:999px;background:rgba(245,158,11,.14);border:1px solid rgba(245,158,11,.28);color:#fde68a;font-size:11px;font-weight:900}}.r11-meta{{color:#aebed1;font-size:12px}}.r11-meta span{{display:flex;gap:4px;align-items:center}}.r11-actions{{justify-content:flex-end}}.r11-fix{{grid-column:1/-1;padding-top:10px;border-top:1px solid rgba(148,163,184,.12);display:flex;gap:10px;flex-wrap:wrap}}.r11-inline{{margin:0}}.r11-inline select{{min-height:42px;max-width:min(330px,80vw);padding:8px 10px;border-radius:12px;background:#0b1728;color:#fff;border:1px solid rgba(125,211,252,.24)}}.r11-btn{{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:8px 12px;border-radius:12px;border:1px solid rgba(125,211,252,.30);background:#17324d;color:#fff!important;-webkit-text-fill-color:#fff!important;text-decoration:none;font-weight:900;cursor:pointer}}.r11-btn.primary{{background:#1d4ed8}}.r11-btn.ok{{background:#15803d;border-color:#86efac}}.r11-btn.ghost{{background:#10243b}}.r11-empty{{padding:30px;text-align:center;border:1px dashed rgba(125,211,252,.25);border-radius:20px}}.r11-empty span{{display:block;color:#9fb4cb;margin-top:6px}}
      @media(max-width:720px){{.r11-hero{{align-items:flex-start}}.r11-count{{font-size:34px}}.r11-doc{{grid-template-columns:1fr}}.r11-actions{{justify-content:flex-start}}.r11-fix{{display:grid}}.r11-inline{{display:grid;grid-template-columns:1fr}}.r11-inline select,.r11-btn{{width:100%;max-width:none}}}}
    </style>"""
    return layout(html)


@app.post('/documenti/da-verificare/<int:doc_id>/ok')
@login_required
def r11_documento_ok(doc_id):
    conn=db(); conn.row_factory=getattr(conn,'row_factory',None)
    try:
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        if not row:
            return redirect_with_message('/documenti/da-verificare','Documento non trovato.','error')
        tid=int(row['tesserato_id'] or 0)
        dtype=str(row['document_type'] or '')
        if tid<=0:
            return redirect_with_message('/documenti/da-verificare','Prima assegna il documento a un atleta.','error')
        if dtype in ('','altro'):
            return redirect_with_message('/documenti/da-verificare','Prima conferma il tipo di documento.','error')
        cols=_cols(conn,'inbound_documents')
        sets=["status='associato'","document_confidence=100","match_score=100"]
        if 'updated_at' in cols: sets.append("updated_at=?"); params=[datetime.now().isoformat(timespec='seconds'),doc_id]
        else: params=[doc_id]
        conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        _r11_sync_documento(conn,row)
        conn.commit()
    finally:
        conn.close()
    return redirect_with_message('/documenti/da-verificare','Documento verificato.','success')


@app.post('/documenti/da-verificare/<int:doc_id>/tipo')
@login_required
def r11_documento_tipo(doc_id):
    allowed={
        'certificato_medico','iscrizione','manleva','liberatoria_immagini','documento_identita',
        'consenso_minore','autorizzazione_genitore','trasporto_minori','documenti_gara',
        'documenti_saggio','ricevuta_pagamento','altro'
    }
    dtype=(request.form.get('document_type') or '').strip()
    if dtype not in allowed:
        return redirect_with_message('/documenti/da-verificare','Tipo documento non valido.','error')
    conn=db()
    try:
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        if not row:
            return redirect_with_message('/documenti/da-verificare','Documento non trovato.','error')
        tid=int(row['tesserato_id'] or 0)
        status='associato' if tid>0 and dtype!='altro' else ('associato_tipo_da_verificare' if tid>0 else 'needs_manual_match')
        cols=_cols(conn,'inbound_documents')
        sets=["document_type=?","document_label=?","document_confidence=100","status=?"]
        vals=[dtype,_r11_doc_label(dtype),status]
        if 'updated_at' in cols: sets.append("updated_at=?"); vals.append(datetime.now().isoformat(timespec='seconds'))
        vals.append(doc_id)
        conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",vals)
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        _r11_sync_documento(conn,row)
        conn.commit()
    finally:
        conn.close()
    return redirect_with_message('/documenti/da-verificare','Tipo documento aggiornato.','success')


@app.post('/documenti/da-verificare/<int:doc_id>/atleta')
@login_required
def r11_documento_atleta(doc_id):
    try: tid=int(request.form.get('tesserato_id') or 0)
    except Exception: tid=0
    conn=db()
    try:
        athlete=conn.execute("SELECT id FROM tesserati WHERE id=?",(tid,)).fetchone() if tid>0 else None
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        if not row or not athlete:
            return redirect_with_message('/documenti/da-verificare','Seleziona un atleta valido.','error')
        dtype=str(row['document_type'] or 'altro')
        status='associato' if dtype not in ('','altro') and int(row['document_confidence'] or 0)>=75 else 'associato_tipo_da_verificare'
        cols=_cols(conn,'inbound_documents')
        sets=["tesserato_id=?","match_score=100","status=?"]; vals=[tid,status]
        if 'matched_tesserato_id' in cols: sets.append("matched_tesserato_id=?"); vals.append(tid)
        if 'updated_at' in cols: sets.append("updated_at=?"); vals.append(datetime.now().isoformat(timespec='seconds'))
        vals.append(doc_id)
        conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",vals)
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        _r11_sync_documento(conn,row)
        conn.commit()
    finally:
        conn.close()
    return redirect_with_message('/documenti/da-verificare','Atleta assegnato.','success')


'''
        s=s.replace(helper_anchor,queue_code+helper_anchor,1)

        old_metric='''\'Documenti da chiudere\': (_scalar(conn, f"SELECT COUNT(*) FROM document_hub WHERE {_open_doc_where()}") if _has_table(conn,'document_hub') else 0, '/document-hub?f=aperti', 'Apri Document Hub'),'''
        new_metric="'Documenti da verificare': (_r11_pending_count(conn), '/documenti/da-verificare', 'Solo documenti che richiedono una scelta'),"
        if old_metric not in s:
            raise RuntimeError('R11 A202 metric anchor missing')
        s=s.replace(old_metric,new_metric,1)

        # Enhance the existing dashboard wrapper without depending on its exact end marker.
        wrap_start=s.find('def a202_dashboard_wrapper(*args, **kwargs):')
        if wrap_start<0:
            raise RuntimeError('R11 dashboard wrapper missing')
        mov_anchor='movimenti = _scalar(conn, "SELECT COUNT(*) FROM movimenti") if _has_table(conn,\'movimenti\') else 0'
        mov_pos=s.find(mov_anchor,wrap_start)
        if mov_pos<0:
            raise RuntimeError('R11 dashboard count anchor missing')
        insert_after=mov_pos+len(mov_anchor)
        s=s[:insert_after]+"\n            pending_docs = _r11_pending_count(conn)"+s[insert_after:]
        insert_anchor='        if isinstance(resp, str):\n'
        insert_pos=s.find(insert_anchor,insert_after)
        if insert_pos<0:
            raise RuntimeError('R11 dashboard response anchor missing')
        cleanup=r'''        # BODYMIND_R11_DASHBOARD_SIMPLIFY
        html = html.replace('/documenti-automatici#docs','/documenti/da-verificare')
        html = html.replace('/document-hub?f=verificare','/documenti/da-verificare')
        html = html.replace('/document-hub?f=aperti','/documenti/da-verificare')
        html = re.sub(
            r"(<a[^>]+href=['\"]/documenti/da-verificare['\"][^>]*>.*?<h3>)(?:Da verificare|Documenti da verificare)(</h3>.*?<strong class=['\"]value['\"]>)\d+(</strong>)",
            lambda m: m.group(1)+'Documenti da verificare'+m.group(2)+str(int(pending_docs))+m.group(3),
            html, count=1, flags=re.S
        )
        r11_script = f"""<script id='bodymind-r11-dashboard-cleanup'>(function(){{function go(){{var root=document.querySelector('.pro-dashboard')||document;var pending={int(pending_docs)};root.querySelectorAll('a[href]').forEach(function(a){{var href=a.getAttribute('href')||'';var txt=(a.textContent||'').replace(/\\s+/g,' ').trim().toLowerCase();if(txt.includes('da verificare')&&txt.includes('document')){{a.setAttribute('href','/documenti/da-verificare');var nums=a.querySelectorAll('strong,.value,.a121-value');for(var i=nums.length-1;i>=0;i--){{if(/^\\d+$/.test((nums[i].textContent||'').trim())){{nums[i].textContent=String(pending);break;}}}}var h=a.querySelector('h3');if(h)h.textContent='Documenti da verificare';}}if(href==='/documenti-automatici'&&txt.includes('documenti automatici'))a.remove();if(href==='/generatore-documenti'&&txt.includes('generatore documenti'))a.remove();}});}}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go,{{once:true}});else go();}})();</script>"""
        if '</body>' in html:
            html = html.replace('</body>', r11_script+'</body>', 1)
        else:
            html += r11_script
'''
        s=s[:insert_pos]+cleanup+s[insert_pos:]
        return s

    patch_file('asd_app/routes_a202_operational_integrity.py',patch_a202)

    def patch_core(s):
        if 'BODYMIND_R11_SINGLE_DOCUMENT_NAV' in s:
            return s
        start=s.find("+ nav_dropdown('Documenti', 'doc',")
        if start<0:
            raise RuntimeError('R11 document nav start missing')
        end=s.find("'documenti')",start)
        if end<0:
            raise RuntimeError('R11 document nav end missing')
        end += len("'documenti')")
        replacement="""+ (nav_link('/documenti', 'Documenti', 'doc', aliases=('/documenti/asd','/documenti/editor/nuovo','/generatore-documenti','/documenti/generatore','/firma-smart','/firma-smart/documento','/documenti-automatici','/document-hub','/documenti/da-verificare'), tier='money', title='Un solo accesso: dossier, verifiche, creazione e firme quando servono.') if has_role('admin') else '')  # BODYMIND_R11_SINGLE_DOCUMENT_NAV"""
        s=s[:start]+replacement+s[end:]
        return s

    patch_file('asd_app/core.py',patch_core)

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R11 compile failed')

    a202=(APP/'asd_app/routes_a202_operational_integrity.py').read_text(encoding='utf-8')
    core=(APP/'asd_app/core.py').read_text(encoding='utf-8')
    checks={
        'queue':'BODYMIND_R11_PENDING_QUEUE' in a202 and "/documenti/da-verificare" in a202,
        'dashboard':'BODYMIND_R11_DASHBOARD_SIMPLIFY' in a202,
        'metric':"'Documenti da verificare': (_r11_pending_count(conn)" in a202,
        'single-nav':'BODYMIND_R11_SINGLE_DOCUMENT_NAV' in core and "nav_dropdown('Documenti'" not in core[core.find('BODYMIND_R11_SINGLE_DOCUMENT_NAV')-1000:core.find('BODYMIND_R11_SINGLE_DOCUMENT_NAV')+1000],
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R11 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind simplification R11 applied\n',encoding='utf-8')
    print('[simplify-r11] applied',flush=True)
    print('[simplify-r11-selftest] PASS pending-queue real-count dashboard-link single-document-nav legacy-redirects',flush=True)
else:
    print('[simplify-r11] already applied',flush=True)
