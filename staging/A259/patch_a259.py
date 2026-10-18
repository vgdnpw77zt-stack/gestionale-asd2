"""A259 deterministic, idempotent source transformer. Runs on clone; NO prod writes."""
from pathlib import Path
import hashlib

FILES=('routes_operator_bodymind.py','routes_quote_incassi.py','core.py')
OP_ANCHOR='''        result=None
        planner_used=False
        trace=[]
'''
OP_INSERT='''        # A259: domande fattuali sui metodi -> contabilità riconciliata, non planner IA.
        from .bodymind_a259_operator_facts import finance_reply as _a259_finance_reply
        try:
            _a259_result = _a259_finance_reply(conn, message)
        except (ValueError, ArithmeticError, RuntimeError) as _a259_exc:
            _log(conn, "system", "A259 financial reconciliation blocked: " + repr(_a259_exc))
            _a259_result = {"text": "Non posso confermare il totale: il registro richiede una verifica di riconciliazione. Non ho modificato nulla.",
                             "mode": "finance_warning", "cloud_ai": False,
                             "links": [{"label": "Contabilità", "href": "/contabilita"}]}
        if _a259_result is not None:
            _log(conn, "assistant", _a259_result.get("text", ""), _a259_result)
            return jsonify(_a259_result)

'''
CSS = '''
/* BODYMIND A259 — CHIARO, ESSENZIALE, iPhone / 12–13 pollici.
   Mantiene i comandi e la brand identity senza sovrapposizioni. */
html body main.bmo .bmo-chat {background:#171a21!important;border:1px solid #343b49!important;border-radius:20px!important;box-shadow:none!important}
html body main.bmo .bmo-messages {gap:16px!important;scrollbar-gutter:stable!important}
html body main.bmo .bmo-msg.bot {color:#ecf0f7!important;font-weight:450!important;line-height:1.56!important}
html body main.bmo .bmo-msg.me {background:#2b313b!important;border:1px solid #414b5a!important;box-shadow:none!important;color:white!important}
html body main.bmo .bmo-hero {background:#181b22!important;border:1px solid #333c4b!important;box-shadow:none!important}
html body main.bmo .bmo-brand-title {font-weight:750!important;letter-spacing:-.015em!important}
html body main.bmo .bmo-top-btn {background:#262d39!important;border:1px solid #465168!important;border-radius:12px!important;box-shadow:none!important}
html body main.bmo .bmo-top-btn:focus-visible,html body main.bmo a:focus-visible,html body main.bmo button:focus-visible {outline:2px solid #78b8f6!important;outline-offset:3px!important}
html body main.bmo .bmo-cash-link {display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:6px!important;padding:10px 13px!important;border:1px solid #5987b6!important;border-radius:13px!important;background:#1a344e!important;color:#e5f2ff!important;text-decoration:none!important;font-size:12px!important;font-weight:750!important;min-height:42px!important}
html body main.bmo .bmo-cash-link:hover {background:#244866!important}
html body main.bmo .bmo-shortcuts {display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:9px 14px;border-bottom:1px solid #333c4c;background:#1c2029}
html body main.bmo .bmo-shortcuts>a {font-size:12px;font-weight:700;color:#cbd8e7;text-decoration:none;padding:6px 8px;border-radius:10px}
html body main.bmo .bmo-shortcuts>a:first-child {background:#24435e;color:#fff}
html body main.bmo .bmo-shortcuts>a:hover {background:#303947}
@media(max-width:800px) {html body main.bmo .bmo-shortcuts {gap:4px;padding:6px 9px;flex-wrap:nowrap;overflow-x:auto}html body main.bmo .bmo-shortcuts>a {flex-shrink:0;padding:7px 8px;white-space:nowrap}}
html body main.bmo .bmo-side.bmo-hidden-tools,html body main.bmo #bmoUploadForm,html body main.bmo #bmoFiles,html body main.bmo #bmoFolder,html body main.bmo #bmoAttachPicker {display:none!important;visibility:hidden!important;width:0!important;height:0!important;max-width:0!important;max-height:0!important;overflow:hidden!important;position:absolute!important;left:-9999px!important}
html body main.bmo .bmo-compose-shell {box-shadow:none!important;border-top:1px solid #333b48!important;background:#191c23!important;min-width:0!important}
html body main.bmo .bmo-compose {box-shadow:none!important;border:1px solid #454e60!important;border-radius:20px!important;background:#272b34!important;min-width:0!important}
html body main.bmo #bmoInput {min-width:0!important;font-size:16px!important;line-height:1.38!important;color:#f5f6fa!important}
html body main.bmo #bmoInput::placeholder {color:#aeb6c5!important;opacity:1!important}
html body main.bmo .bmo-send {background:#315d87!important;border-color:#588ab7!important}
@media (max-width:800px) {
  html body main.bmo .bmo-hero {padding:8px 10px!important;min-height:58px!important;flex:0 0 58px!important;height:58px!important}
  html body main.bmo .bmo-brand-title {font-size:16px!important;line-height:1.25!important}
  html body main.bmo .bmo-brand-sub {display:none!important}
  html body main.bmo .bmo-brand {min-width:0!important;flex:1 1 auto!important}
  html body main.bmo .bmo-brand-copy {min-width:0!important}
  html body main.bmo .bmo-top-actions {gap:5px!important;flex-shrink:0!important}
  html body main.bmo .bmo-top-btn {width:38px!important;height:38px!important;min-width:38px!important;padding:0!important}
  html body main.bmo .bmo-top-btn span {display:none!important}
  html body main.bmo .bmo-chat {border:0!important;border-radius:0!important}
  html body main.bmo .bmo-messages {padding:14px 12px 8px!important;gap:12px!important;scrollbar-gutter:auto!important}
  html body main.bmo .bmo-msg-row {min-width:0!important;gap:7px!important}
  html body main.bmo .bmo-msg {max-width:calc(100% - 38px)!important;font-size:14.5px!important;line-height:1.53!important}
  html body main.bmo .bmo-compose-shell {padding:7px 9px max(9px,env(safe-area-inset-bottom))!important;flex:0 0 auto!important;overflow:hidden!important}
  html body main.bmo .bmo-compose {display:grid!important;grid-template-columns:40px minmax(0,1fr) 40px 40px!important;gap:5px!important;padding:6px!important;border-radius:18px!important}
  html body main.bmo .bmo-compose>.bmo-attach, html body main.bmo .bmo-compose>.bmo-mic,html body main.bmo .bmo-compose>.bmo-send {width:40px!important;min-width:40px!important;max-width:40px!important;height:42px!important;min-height:42px!important;border-radius:12px!important}
  html body main.bmo #bmoInput {grid-column:2!important;width:100%!important;max-width:100%!important;min-width:0!important;min-height:42px!important;height:42px!important;padding:9px 5px!important;font-size:16px!important;resize:none!important}
  html body main.bmo .bmo-starters {display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important}
  html body main.bmo .bmo-starters button,html body main.bmo .bmo-starters .bmo-cash-link {min-width:0!important;width:100%!important;max-width:none!important;border-radius:12px!important;min-height:44px!important;text-align:left!important;white-space:normal!important}
  html body main.bmo .bmo-empty {padding:12px 9px!important}
}
@media (min-width:801px) and (max-width:1366px) {
  html body main.bmo .bmo-hero {padding:10px 14px!important}
  html body main.bmo .bmo-grid {grid-template-columns:minmax(0,1fr)!important}
  html body main.bmo .bmo-messages {padding:16px!important}
  html body main.bmo .bmo-compose-shell {padding:10px 12px!important}
}
@media (prefers-reduced-motion:reduce) {
  html body main.bmo *,html body main.bmo *::before,html body main.bmo *::after {animation-duration:.01ms!important;transition-duration:.01ms!important}
}
'''

CASH_VIEW = '''

# A259: scorciatoia per incassi in contanti su smartphone; riusa la route di
# registrazione consolidata invece di creare un secondo motore di pagamenti.
@app.get('/quote-incassi/incasso-rapido')
@admin_required
def a259_incasso_rapido():
    conn=db()
    try:
        people=conn.execute("SELECT id,nome,cognome FROM tesserati WHERE COALESCE(attivo,1)=1 ORDER BY cognome,nome").fetchall()
    finally:
        conn.close()
    mm,yy=current_month_year()
    options=''.join(f"<option value='{int(t['id'])}'>{e(str(t['cognome'] or '')+' '+str(t['nome'] or ''))}</option>" for t in people)
    return layout(f"""
    <style id='a259-fastcash-style'>
      .a259-cash {{max-width:740px;margin:20px auto 70px;color:#f2f5fc}}
      .a259-cash header {{padding:20px 22px;border-radius:20px;border:1px solid #344761;background:#192638}}
      .a259-cash header small {{color:#b9cbe0;letter-spacing:.08em;text-transform:uppercase}}
      .a259-cash h1 {{font-size:clamp(23px,4vw,32px);margin:7px 0;line-height:1.2}}
      .a259-cash p {{color:#c2cedf;line-height:1.5}}
      .a259-cash form {{margin-top:15px;display:grid;gap:13px;padding:22px;border-radius:20px;border:1px solid #374961;background:#182131}}
      .a259-cash label {{display:block;font-weight:700;font-size:14px;color:#eaf2ff}}
      .a259-cash input,.a259-cash select {{display:block;width:100%;min-height:46px;box-sizing:border-box;padding:10px;border:1px solid #61758e;border-radius:11px;background:#0e1827;color:#fff;font:inherit;font-size:16px;margin-top:6px}}
      .a259-cash .row {{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
      .a259-cash button {{min-height:50px;border:0;background:#235a8c;color:#fff;border-radius:12px;font:inherit;font-weight:800;cursor:pointer}}
      .a259-cash button:disabled {{opacity:.65;cursor:wait}}
      .a259-cash a {{color:#b5d9ff}}
      @media(max-width:520px){{.a259-cash {{margin:8px auto 80px}}.a259-cash header,.a259-cash form{{padding:16px}}.a259-cash .row{{grid-template-columns:1fr 1fr}}}}
    </style>
    <main class='a259-cash'>
      <header><small>Segreteria · Incasso rapido</small><h1>Registra una quota in contanti</h1>
        <p>Dal telefono, senza passare per la chat. Usa il motore ufficiale Quote & Incassi: ricevuta progressiva e saldo saranno aggiornati solo dopo il salvataggio.</p></header>
      <form id='a259-cash-form' method='post' action='/quote-incassi/incasso/0'>
        {csrf_input()}
        <label>Atleta<select id='a259-athlete' required><option value=''>Scegli la ragazza</option>{options}</select></label>
        <div class='row'><label>Mese<input name='mese' type='number' min='1' max='12' value='{mm}' required></label><label>Anno<input name='anno' type='number' min='2020' max='2100' value='{yy}' required></label></div>
        <label>Importo ricevuto (€)<input name='importo' type='number' inputmode='decimal' min='0.01' max='99999' step='0.01' placeholder='Es. 50,00' required></label>
        <input name='metodo' value='contanti' type='hidden'>
        <label>Note (facoltative)<input name='note' maxlength='180' placeholder='Es. quota mensile'></label>
        <button id='a259-cash-save' type='submit'>Conferma incasso in contanti</button>
        <p style='margin:0;font-size:12px'>Verifica importo e mensilità prima di confermare. Per rettifiche e annullamenti usa <a href='/pagamenti'>Pagamenti</a>.</p>
      </form>
    </main>
    <script>(function(){{
      const form=document.getElementById('a259-cash-form');
      const athlete=document.getElementById('a259-athlete');
      const save=document.getElementById('a259-cash-save');
      if(!form||!athlete||!save)return;
      form.addEventListener('submit',function(ev){{
        if(!form.reportValidity()){{ev.preventDefault();return;}}
        const tid=Number(athlete.value);
        if(!Number.isSafeInteger(tid)||tid<=0){{ev.preventDefault();athlete.focus();return;}}
        const name=athlete.selectedOptions[0].textContent;
        const amount=form.elements['importo'].value;
        const m=form.elements['mese'].value,y=form.elements['anno'].value;
        if(!window.confirm('Confermi incasso CONTANTI di € '+amount+' per '+name+' — '+m+'/'+y+'?')){{ev.preventDefault();return;}}
        form.action='/quote-incassi/incasso/'+encodeURIComponent(String(tid));
        save.disabled=true;
        save.textContent='Registrazione in corso…';
      }});
    }})();</script>
    """)
'''


def patch(root):
    root=Path(root)
    original={f:(root/f).read_text(encoding='utf-8') for f in FILES}
    EXPECTED={
      'routes_operator_bodymind.py':'96bbf726d4f5aeaa0d812512af2a6b4b1a0c8ad655ecc65ea369e6d09827db97',
      'routes_quote_incassi.py':'e8eb09c84d44238590e3542266f12239d43be092a39cf70e0e4858320475ee49',
      'core.py':'a1f76ee6434b5fba81e1085437b6a0b0d4cd6cf0ba8fc18805f921ab5bad3455',
    }
    for filename, body in original.items():
        current=hashlib.sha256(body.encode()).hexdigest()
        if current != EXPECTED[filename] and 'A259' not in body:
            raise RuntimeError('STOP A259: SHA base differente per '+filename)
    op=original['routes_operator_bodymind.py']
    if '# A259: domande fattuali' not in op:
        assert op.count(OP_ANCHOR)==1
        op=op.replace(OP_ANCHOR,OP_INSERT+OP_ANCHOR,1)
    css='\n'+CSS.replace('{','{{').replace('}','}}')+'\n'
    if 'BODYMIND A259 — CHIARO' not in op:
        anchor='\n</style>\n\n    <main class="bmo">'
        assert op.count(anchor)==1
        op=op.replace(anchor,css+anchor,1)
    # Shorter placeholder avoids two-line clipping in iPhone compact composer.
    op=op.replace('placeholder="Messaggio a Segreteria BodyMind"',
                  'placeholder="Scrivi un messaggio…"',1)
    if 'class="bmo-shortcuts"' not in op:
        anchor_nav='<div class="bmo-chat">\n          <div class="bmo-messages"'
        assert op.count(anchor_nav)==1
        op=op.replace(anchor_nav, '<div class="bmo-chat">\n          <nav class="bmo-shortcuts" aria-label="Azioni rapide">' +
                      '<a href="/quote-incassi/incasso-rapido">💶 Registra contanti</a>' +
                      '<a href="/pagamenti">Pagamenti</a>' +
                      '<a href="/ricevute">Ricevute</a></nav>\n          <div class="bmo-messages"', 1)
    if 'class="bmo-cash-link"' not in op:
        marker='<button data-q="Fammi un riepilogo operativo della segreteria">Riepilogo segreteria</button>'
        assert op.count(marker)==1
        op=op.replace(marker,marker+'\n                  <a class="bmo-cash-link" href="/quote-incassi/incasso-rapido">💶 Registra contanti</a>',1)
    cash=original['routes_quote_incassi.py']
    if 'def a259_incasso_rapido' not in cash:
        cash += CASH_VIEW
    core=original['core.py']
    tl='''   if path == "/cuore-operativo" or path.startswith("/cuore-operativo/") or path == "/timeline" or path.startswith("/timeline/") or (path.startswith("/tesserati/") and path.endswith("/timeline")):
      items.append(("/timeline", "Timeline", "Eventi e log operativi"))'''
    if 'A259: timeline hidden' not in core:
        assert core.count(tl)==1
        core=core.replace(tl,'   # A259: timeline hidden from quickdock. Data/audit routes remain intact.',1)
    result={'routes_operator_bodymind.py':op,'routes_quote_incassi.py':cash,'core.py':core}
    for f,body in result.items():
        compile(body, str(root/f), 'exec')
        (root/f).write_text(body,encoding='utf-8')
    return {f:{'before':hashlib.sha256(original[f].encode()).hexdigest(),
               'after':hashlib.sha256(result[f].encode()).hexdigest(),
               'changed':original[f]!=result[f]} for f in FILES}

if __name__ == '__main__':
    import argparse, json
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True)
    a=ap.parse_args();print(json.dumps(patch(a.root),indent=2))