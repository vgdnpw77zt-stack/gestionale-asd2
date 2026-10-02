# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, re, shutil, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r73_mobile_operator_mu')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup(p: Path):
    rel=p.relative_to(APP)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)

def counts():
    out={}
    if not DB.exists():
        return out
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                out[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
    finally:
        conn.close()
    return out

before=counts()

# 1) Operator mobile UX + more autonomous multi-step planner.
OP=APP/'asd_app/routes_operator_bodymind.py'
s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY' not in s:
    backup(OP)

    css_anchor='.bmo-compose textarea{{min-height:48px;max-height:150px;resize:vertical;border-radius:15px;padding:12px 14px;background:#081729;color:#fff;border:1px solid rgba(125,211,252,.19);font:inherit}}'
    css_extra=css_anchor+'''
    /* BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY */
    @media(max-width:800px){
      .bmo-chat{min-height:calc(100dvh - 150px)!important;height:calc(100dvh - 150px)!important;overflow:hidden!important}
      .bmo-messages{max-height:none!important;min-height:0!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;padding-bottom:18px!important}
      .bmo-compose-shell{position:sticky!important;bottom:0!important;z-index:80!important;background:rgba(5,12,23,.98)!important;padding-bottom:env(safe-area-inset-bottom)!important}
      .bmo-compose{position:relative!important;bottom:auto!important}
      .bmo-compose textarea{resize:none!important;max-height:118px!important}
    }'''
    if css_anchor not in s:
        raise RuntimeError('R73 operator composer CSS anchor missing')
    s=s.replace(css_anchor,css_extra,1)

    js_anchor="      function addMsg(text,who='bot',data={{}}){{"
    js_helper="""      function bodymindKeepComposerVisible(){
        try{
          messages.scrollTop=messages.scrollHeight;
          if(window.matchMedia&&window.matchMedia('(max-width:800px)').matches){
            const shell=document.querySelector('.bmo-compose-shell');
            if(shell) shell.scrollIntoView({block:'end',behavior:'smooth'});
          }
        }catch(e){}
      }
"""
    if js_anchor not in s:
        raise RuntimeError('R73 operator addMsg anchor missing')
    s=s.replace(js_anchor,js_helper+js_anchor,1)
    old_scroll="        requestAnimationFrame(()=>{{messages.scrollTop=messages.scrollHeight}});"
    new_scroll="        requestAnimationFrame(()=>{{bodymindKeepComposerVisible()}});"
    if old_scroll not in s:
        raise RuntimeError('R73 operator scroll anchor missing')
    s=s.replace(old_scroll,new_scroll,1)

    old_finally="        }}finally{{send.disabled=false;input.focus()}}"
    new_finally="        }}finally{{send.disabled=false;input.focus();setTimeout(bodymindKeepComposerVisible,80)}}"
    if old_finally not in s:
        raise RuntimeError('R73 operator ask/focus anchor missing')
    s=s.replace(old_finally,new_finally,1)

    if 'for agent_step in range(3):' not in s:
        raise RuntimeError('R73 cloud loop anchor missing')
    s=s.replace('for agent_step in range(3):','for agent_step in range(5):',1)
    s=s.replace('if tool in discovery_tools and agent_step<2:','if tool in discovery_tools and agent_step<4:',1)

    old_prompt=(
        '"Scegli UNO strumento reale e preferisci direttamente lo strumento operativo corretto. Usa discover_capabilities solo se gli elementi pertinenti non bastano davvero. "'
    )
    new_prompt=(
        '"Porta a termine la richiesta nello stesso turno quando gli strumenti disponibili lo consentono. "'
        '"Puoi concatenare più passaggi tramite il ciclo agente: scegli adesso il prossimo strumento realmente utile e usa discover_capabilities solo se gli elementi pertinenti non bastano davvero. "'
        '"Non chiedere conferme o dettagli per controlli, letture, ricerche, classificazioni, sincronizzazioni sicure o preparazione del lavoro quando il dato è già ricavabile dal gestionale o dal contesto. "'
        '"Chiedi una precisazione soltanto se manca un dato indispensabile o ci sono più identità plausibili. "'
        '"Le conferme restano obbligatorie per cancellazioni, fusioni, modifiche economiche, invii esterni o altre operazioni irreversibili/sensibili. "'
    )
    if old_prompt not in s:
        raise RuntimeError('R73 planner prompt anchor missing')
    s=s.replace(old_prompt,new_prompt,1)
    OP.write_text(s,encoding='utf-8')

# 2) Global MU presence: uploaded/accepted MU must never be shown as "not generated".
COH=APP/'asd_app/routes_document_coherence_r41.py'
c=COH.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R73_GLOBAL_MU_PRESENCE' not in c:
    backup(COH)
    start=c.find('def _mu_state(tid):')
    end=c.find('def _replace_contextual_not_generated',start)
    if start<0 or end<0:
        raise RuntimeError('R73 MU state function anchor missing')
    new_func=r'''# BODYMIND_R73_GLOBAL_MU_PRESENCE
def _mu_state(tid):
    if tid<=0:
        return None
    conn=db()
    try:
        states=[]
        # Dossier rows: generated OR uploaded documents live here.
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
            rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall()
            for r in rows:
                hay=' '.join(str(r[k] or '').strip().lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
                if not any(x in hay for x in _MU_ALIASES):
                    continue
                status=str(r['status'] or '').strip().lower() if 'status' in r.keys() else ''
                states.append('verified' if status in _TRUSTED else 'pending')

        # Inbound rows matter too: a MU can have been uploaded/accepted without being "generated".
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone():
            rows=conn.execute("SELECT * FROM inbound_documents WHERE coalesce(tesserato_id,0)=? ORDER BY id DESC",(tid,)).fetchall()
            for r in rows:
                keys=set(r.keys())
                dtype=str(r['document_type'] or '').strip().lower() if 'document_type' in keys else ''
                hay=' '.join(str(r[k] or '').strip().lower() for k in ('document_type','original_filename','filename','saved_path') if k in keys)
                if dtype not in _MU_ALIASES and not any(x in hay for x in _MU_ALIASES):
                    continue
                status=str(r['status'] or '').strip().lower() if 'status' in keys else ''
                conf=int(r['document_confidence'] or 0) if 'document_confidence' in keys else 0
                match=int(r['match_score'] or 0) if 'match_score' in keys else 0
                trusted=status in ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved')
                associated=status=='associato' and (conf>=95 or match>=95)
                states.append('verified' if (trusted or associated) else 'pending')

        if 'verified' in states:
            return 'verified'
        if states:
            return 'pending'
        return None
    finally:
        conn.close()

'''
    c=c[:start]+new_func+c[end:]

    # Wider wording coverage, still contextual to the MU card/label.
    c=c.replace(
        "r'(?i)(Modulo\\s+Unico(?:\\s+MU[- ]?2026(?:\\.1)?)?\\s*(?:[:·\\-]\\s*)?)(non\\s+(?:ancora\\s+)?generat[oa])'",
        "r'(?i)(Modulo\\s+Unico(?:\\s+MU[- ]?2026(?:\\.1)?)?\\s*(?:[:·\\-]\\s*)?)(?:non\\s+(?:ancora\\s+)?generat[oa]|mancante|non\\s+presente)'"
    )
    COH.write_text(c,encoding='utf-8')

# 3) Mobile athlete deletion: expose the existing protected delete control, never create a bypass route.
MOB=APP/'asd_app/routes_document_coherence_r41.py'
m=MOB.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R73_MOBILE_DELETE_VISIBILITY' not in m:
    marker="""        # BODYMIND_R73_MOBILE_DELETE_VISIBILITY
        if request.path=='/mobile' or request.path.startswith('/tesserati'):
            patch="""<style id='BODYMIND_R73_MOBILE_DELETE_VISIBILITY'>
@media(max-width:800px){
  form[action*='elimina' i],form[action*='delete' i],a[href*='elimina' i],a[href*='delete' i],
  button[name*='elimina' i],button[data-action*='delete' i],button[data-action*='elimina' i]{
    display:inline-flex!important;visibility:visible!important;opacity:1!important;pointer-events:auto!important
  }
}
</style>
<script>
(function(){
 if(!window.matchMedia||!window.matchMedia('(max-width:800px)').matches)return;
 document.querySelectorAll('button,a,input[type=submit]').forEach(function(el){
   var txt=(el.textContent||el.value||'').toLowerCase();
   var href=(el.getAttribute('href')||'').toLowerCase();
   var action=((el.closest('form')||{}).action||'').toLowerCase();
   if(txt.indexOf('elimina')>=0||txt.indexOf('cancella')>=0||href.indexOf('elimina')>=0||href.indexOf('delete')>=0||action.indexOf('elimina')>=0||action.indexOf('delete')>=0){
     el.style.setProperty('display','inline-flex','important');
     el.style.setProperty('visibility','visible','important');
     el.style.setProperty('opacity','1','important');
   }
 });
})();
</script>"""
            html=html.replace('</body>',patch+'</body>',1) if '</body>' in html else html+patch
"""
    anchor="        ua=str(request.headers.get('User-Agent') or '')"
    if anchor not in m:
        raise RuntimeError('R73 mobile visibility insertion anchor missing')
    m=m.replace(anchor,marker+"
"+anchor,1)
    MOB.write_text(m,encoding='utf-8')

for p in (OP,COH):
    if not compileall.compile_file(str(p),quiet=1):
        raise RuntimeError('R73 compile failed: '+str(p))

# Runtime QA: no business mutation.
sys.path.insert(0,str(APP))
from asd_app.verified_mu_sync_core_r68 import _identity_matches
same={'nome':'LUDOVICA','cognome':'ANNUNZIATO','codice_fiscale':'NNNLVC14D56D972N','data_nascita':'2014-04-16'}
conflict={'first_name':'Ludovica','last_name':'Annunziato','codice_fiscale':'RSSMRA80A01H501U','birth_date':'2014-04-16'}
ok={'first_name':'Ludovica','last_name':'Annunziato','codice_fiscale':'NNNLVC14D56D972N','birth_date':'2014-04-16'}
no_cf={'first_name':'Ludovica','last_name':'Annunziato','birth_date':'2014-04-16'}
checks={}
checks['cf_conflict_blocked']=_identity_matches(same,conflict)==(False,'cf_conflict')
checks['cf_equal_allowed']=_identity_matches(same,ok)[0] is True
checks['name_birth_without_doc_cf_allowed']=_identity_matches(same,no_cf)[0] is True
optext=OP.read_text(encoding='utf-8',errors='replace')
cotext=COH.read_text(encoding='utf-8',errors='replace')
checks['mobile_composer']='BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY' in optext and 'bodymindKeepComposerVisible' in optext
checks['five_step_agent']='for agent_step in range(5):' in optext
checks['autonomy_prompt']='Porta a termine la richiesta nello stesso turno' in optext
checks['global_mu_presence']='BODYMIND_R73_GLOBAL_MU_PRESENCE' in cotext and 'inbound_documents' in cotext
checks['mobile_delete_visibility']='BODYMIND_R73_MOBILE_DELETE_VISIBILITY' in cotext

after=counts()
checks['business_counts_unchanged']=before==after
integrity='missing'; fk=-1
if DB.exists():
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()
checks['db_integrity']=integrity.lower()=='ok' and fk==0
failed=[k for k,v in checks.items() if not v]
print('[r73-mobile-operator-mu] checks='+repr(checks),flush=True)
print('[r73-mobile-operator-mu] counts_before='+repr(before)+' counts_after='+repr(after)+' integrity='+integrity+' fk='+str(fk),flush=True)
if failed:
    raise RuntimeError('R73 QA failed '+repr(failed))
print('[r73-mobile-operator-mu-selftest] PASS cf-hard-gate mobile-composer 5-step-autonomy global-MU-presence mobile-delete-visible data-safe',flush=True)
