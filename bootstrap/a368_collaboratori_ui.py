"""Presentation-only repair. No database access and no changes to POST handlers."""
from flask import request

CSS = '''
#a368-dialog {position:fixed!important;inset:0 0 0 auto!important;margin:0!important;width:min(760px,100vw)!important;height:100dvh!important;max-height:100dvh!important;max-width:100vw!important;padding:0!important;border:0!important;background:#0b1a2e!important;color:#f1f5f9!important;overflow:auto!important;box-sizing:border-box!important;z-index:10000!important}
#a368-dialog::backdrop {background:rgba(2,6,23,.75)}
#a368-dialog .drawer-shell {display:block!important;position:static!important;inset:auto!important}
#a368-dialog .drawer-backdrop {display:none!important}
#a368-dialog .drawer-panel {position:static!important;width:100%!important;height:auto!important;min-height:100%;box-sizing:border-box;padding:24px!important;background:#0b1a2e!important;overflow:visible!important}
#a368-dialog .drawer-head {display:flex;justify-content:space-between;gap:16px;align-items:start}
#a368-dialog .drawer-close {font-size:28px;color:white!important;padding:8px;text-decoration:none}
#a368-dialog .form-row {display:grid!important;grid-template-columns:1fr!important;gap:16px!important}
#a368-dialog input:not([type=hidden]):not([type=checkbox]),#a368-dialog select,#a368-dialog textarea {display:block;width:100%;box-sizing:border-box;min-height:46px;background:#fff!important;color:#102033!important;-webkit-text-fill-color:#102033!important;border:1px solid #64748b!important;border-radius:8px;padding:12px;font-size:16px}
#a368-dialog button {background:#2563eb!important;color:white!important;min-height:48px;border:0;border-radius:8px;padding:12px;font-weight:700}
#a368-dialog label,#a368-dialog .form-hint {color:#e2e8f0!important;line-height:1.5}
#a368-dialog .card {background:transparent!important;border:0!important;padding:0!important;box-shadow:none!important}
#a368-dialog .card > .kicker,#a368-dialog .card > .section-title {display:none!important}
html body main.content .bm19-wrap .bm19-card,html body main.content .bm19-wrap .bm19-grid>div {background:#10243b!important;color:#f1f5f9!important;border-color:#526780!important}
html body main.content .bm19-wrap :is(h1,h2,h3,b,strong,label,p,small,.note) {color:#e2e8f0!important;-webkit-text-fill-color:#e2e8f0!important;opacity:1!important}
html body main.content .bm19-wrap .note {background:#172f49!important}
html body main.content .bm19-wrap :is(input,select,textarea),html body main.content .bm19-wrap option {background:#fff!important;color:#102033!important;-webkit-text-fill-color:#102033!important}
#a368-checklist {padding:20px;border:1px solid #64748b;border-radius:14px;background:#10243b;color:#fff;line-height:1.6}
#a368-checklist li {margin:8px 0}
'''
JS = '''
(()=>{
 const shells=[...document.querySelectorAll('.drawer-shell')];
 if(location.pathname==='/collaboratori') {
   const active=shells.find(s=>s.classList.contains('open'));
   shells.forEach(s=>{if(s!==active)s.remove()});
   if(active){
     const d=document.createElement('dialog'); d.id='a368-dialog';
     d.setAttribute('aria-label',active.querySelector('h3')?.textContent||'Collaboratori');
     document.body.append(d);d.append(active);
     const close=active.querySelector('.drawer-close');
     if(close) close.setAttribute('aria-label','Chiudi e torna ai collaboratori');
     d.addEventListener('cancel',e=>{e.preventDefault();if(close)location.href=close.href});
     d.addEventListener('click',e=>{if(e.target===d&&close)location.href=close.href});
     const fields=active.querySelectorAll('input:not([type=hidden]):not([type=checkbox]),select,textarea');
     fields.forEach((f,i)=>{const label=f.placeholder||(f.name==='collaboratore_id'?'Collaboratore':f.name);if(!f.closest('label')){f.id=f.id||'a368-field-'+i;const l=document.createElement('label');l.htmlFor=f.id;l.textContent=label;f.before(l)}});
     if(d.showModal)d.showModal();else d.setAttribute('open','');
   }
 }
 const wrap=document.querySelector('.bm19-wrap');
 if(wrap){
   const box=document.createElement('section');box.id='a368-checklist';
   const h=document.createElement('h2');h.textContent='Cosa resta da fare nel periodo';box.append(h);
   const p=document.createElement('p');p.textContent='Questa è la checklist degli stati registrati: “Da verificare” non significa obbligo accertato. Gli importi a zero non confermano da soli che un adempimento non sia dovuto. Il salvataggio non effettua invii né versamenti.';box.append(p);
   const list=document.createElement('ul');box.append(list);
   const names=['autodichiarazione_soglie','contratto_stato','comunicazione_stato','gestione_separata_stato','lul_stato','f24_stato'];
   function render(){list.replaceChildren();names.forEach(n=>{const s=wrap.querySelector('select[name="'+n+'"]');if(!s)return;const li=document.createElement('li');const title=s.closest('label').firstChild.textContent.trim();const status=s.selectedOptions[0].textContent;const pending=['da_acquisire','da_verificare','da_preparare','da_versare'].includes(s.value);li.textContent=(pending?'Da gestire — ':'Stato indicato — ')+title+': '+status;list.append(li)})}
   wrap.querySelector('form[method="post"]').before(box);render();
   names.forEach(n=>wrap.querySelector('select[name="'+n+'"]').addEventListener('change',render));
 }
})();
'''

def install(app):
    if app.extensions.get('a368_ui'):
        return
    app.extensions['a368_ui'] = True
    @app.after_request
    def a368_ui(response):
        if (request.path == '/collaboratori' or request.path.startswith('/collaboratori/adempimenti/')) and response.status_code == 200 and response.mimetype == 'text/html':
            html = response.get_data(as_text=True)
            if '</body>' in html and 'id="a368-ui"' not in html:
                html = html.replace('</body>', '<style id="a368-ui">'+CSS+'</style><script>'+JS+'</script></body>')
                response.set_data(html)
                response.headers['Cache-Control'] = 'private, no-store'
        return response
