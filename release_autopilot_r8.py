from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_AUTOPILOT_R8'
BACKUPS=Path('/data/release_backups/20260926_autopilot_r8')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    rel='asd_app/routes_bodymind_fix49.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R8 target missing: '+rel)
    s=p.read_text(encoding='utf-8')

    # Remove the temporary R7 global fetch monkeypatch: retrying POST uploads
    # can duplicate a document if the server saved it but the response was lost.
    tag='/* BODYMIND_R7_UPLOAD_RESILIENCE'
    start=s.find(tag)
    if start>=0:
        end=s.find('})();',start)
        if end<0:
            raise RuntimeError('R8 could not delimit R7 injection')
        end+=5
        while end<len(s) and s[end] in '\r\n':
            end+=1
        backup(rel)
        s=s[:start]+s[end:]

    old_fetch="fetch('/autopilot/upload',{method:'POST',body:fd,credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest','X-BodyMind-Autopilot':'49-mobile'}})"
    new_fetch="fetch('/autopilot/upload',{method:'POST',body:fd,credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'XMLHttpRequest','X-BodyMind-Autopilot':'r8-mobile'}})"
    if new_fetch not in s:
        if old_fetch in s:
            s=s.replace(old_fetch,new_fetch,1)
        elif "X-BodyMind-Autopilot':'r7-mobile'" in s:
            s=s.replace("X-BodyMind-Autopilot':'r7-mobile'","X-BodyMind-Autopilot':'r8-mobile'",1)
        else:
            raise RuntimeError('R8 fetch anchor missing')

    old_handlers="fileBtn.addEventListener('click',()=>!busy&&filePick.click()); cameraBtn.addEventListener('click',()=>!busy&&cameraPick.click()); filePick.addEventListener('change',()=>{send(filePick.files);filePick.value='';}); cameraPick.addEventListener('change',()=>{send(cameraPick.files);cameraPick.value='';});"
    new_handlers="""form.addEventListener('submit',ev=>{ev.preventDefault();ev.stopPropagation();return false;});
fileBtn.addEventListener('click',()=>{if(!busy){filePick.value='';filePick.click();}});
cameraBtn.addEventListener('click',()=>{if(!busy){cameraPick.value='';cameraPick.click();}});
filePick.addEventListener('change',async()=>{const chosen=Array.from(filePick.files||[]);if(chosen.length)await send(chosen);});
cameraPick.addEventListener('change',async()=>{const chosen=Array.from(cameraPick.files||[]);if(chosen.length)await send(chosen);});
window.addEventListener('beforeunload',ev=>{if(busy){ev.preventDefault();ev.returnValue='';}});"""
    if new_handlers not in s:
        if old_handlers not in s:
            raise RuntimeError('R8 upload handler anchor missing')
        s=s.replace(old_handlers,new_handlers,1)

    old_timers="timers=[setTimeout(()=>busy&&msg('Leggo il documento e cerco l’atleta…','busy'),2200),setTimeout(()=>busy&&msg('OCR in corso…','busy'),6000),setTimeout(()=>busy&&msg('Aggiorno associazione e scadenza…','busy'),12000)];"
    new_timers="timers=[setTimeout(()=>busy&&msg('Leggo il documento e cerco l’atleta…','busy'),2200),setTimeout(()=>busy&&msg('OCR in corso…','busy'),6000),setTimeout(()=>busy&&msg('Aggiorno associazione e scadenza…','busy'),12000),setTimeout(()=>busy&&msg('Elaborazione ancora in corso: non chiudere la pagina…','busy'),25000),setTimeout(()=>busy&&msg('Il PDF richiede più tempo del normale, ma sto ancora lavorando…','busy'),60000)];"
    if new_timers not in s and old_timers in s:
        s=s.replace(old_timers,new_timers,1)

    old_catch="}catch(e){clearTimers();setBusy(false);msg('Import non riuscito. Puoi riprovare subito senza ricaricare.','err');results.innerHTML='<div class=\"errors\">'+esc(e&&e.message?e.message:'Errore di rete/server')+'</div>';}"
    new_catch="}catch(e){clearTimers();setBusy(false);const why=(e&&e.message)?String(e.message):'Errore di rete/server';msg('Connessione interrotta durante l’import. Riseleziona il file e riprova: non faccio retry automatici per evitare duplicati.','err');results.innerHTML='<div class=\"errors\">'+esc(why)+'</div>';}"
    if new_catch not in s and old_catch in s:
        s=s.replace(old_catch,new_catch,1)

    backup(rel)
    p.write_text(s,encoding='utf-8')

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R8 compile failed')

    live=p.read_text(encoding='utf-8')
    required=[
        "X-BodyMind-Autopilot':'r8-mobile'",
        "cache:'no-store'",
        "form.addEventListener('submit',ev=>{ev.preventDefault()",
        "filePick.addEventListener('change',async()",
        "cameraPick.addEventListener('change',async()",
        "beforeunload",
        "Elaborazione ancora in corso",
        "non faccio retry automatici per evitare duplicati",
    ]
    missing=[x for x in required if x not in live]
    forbidden=['BODYMIND_R7_UPLOAD_RESILIENCE','attempt<=3','Riprovo automaticamente']
    present=[x for x in forbidden if x in live]
    if missing or present:
        raise RuntimeError('R8 selftest missing='+repr(missing)+' forbidden='+repr(present))

    MARKER.write_text('BodyMind Autopilot R8 Chrome-safe upload applied\n',encoding='utf-8')
    print('[autopilot-r8] applied',flush=True)
    print('[autopilot-r8-selftest] PASS no-auto-retry preserve-file-during-fetch submit-guard no-store long-progress beforeunload',flush=True)
else:
    print('[autopilot-r8] already applied',flush=True)
