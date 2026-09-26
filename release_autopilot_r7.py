from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_AUTOPILOT_R7'
BACKUPS=Path('/data/release_backups/20260926_autopilot_r7')

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
    s=p.read_text(encoding='utf-8')
    old="""async function send(files){
files=Array.from(files||[]).filter(Boolean); if(!files.length||busy)return;
const max={{max_upload_mb|int}}*1024*1024, over=files.find(f=>f.size>max); if(over){msg('File troppo grande: '+over.name+'. Limite {{max_upload_mb|int}} MB.','err');return;}
setBusy(true); results.innerHTML=''; msg('Analizzo '+files.length+' file…','busy');
timers=[setTimeout(()=>busy&&msg('Leggo il documento e cerco l’atleta…','busy'),2200),setTimeout(()=>busy&&msg('OCR in corso…','busy'),6000),setTimeout(()=>busy&&msg('Aggiorno associazione e scadenza…','busy'),12000)];
const fd=new FormData(); const csrf=form.querySelector('input[name="csrf_token"]'); if(csrf)fd.append('csrf_token',csrf.value); files.forEach(f=>fd.append('files',f,f.name));
try{
const r=await fetch('/autopilot/upload',{method:'POST',body:fd,credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest','X-BodyMind-Autopilot':'49-mobile'}});
const txt=await r.text(); let data; try{data=JSON.parse(txt)}catch(_){data={ok:false,error:'Risposta server non valida (HTTP '+r.status+')'};}
clearTimers(); setBusy(false); render(data||{});
if(!r.ok||!data||data.ok===false){msg((data&&data.error)||'Import non riuscito. Puoi riprovare subito.','err');return;}
const p=[]; if(data.associati)p.push(data.associati+' associati'); if(data.certificati_aggiornati)p.push(data.certificati_aggiornati+' certificati aggiornati'); if(data.conferma)p.push(data.conferma+' da confermare'); if(data.verificare)p.push(data.verificare+' da verificare'); if(data.rifiutati)p.push(data.rifiutati+' non importati'); if(data.elapsed_ms)p.push((data.elapsed_ms/1000).toFixed(1)+' s');
msg(p.join(' · ')||'Import completato','ok');
}catch(e){clearTimers();setBusy(false);msg('Import non riuscito. Puoi riprovare subito senza ricaricare.','err');results.innerHTML='<div class="errors">'+esc(e&&e.message?e.message:'Errore di rete/server')+'</div>';}
}
fileBtn.addEventListener('click',()=>!busy&&filePick.click()); cameraBtn.addEventListener('click',()=>!busy&&cameraPick.click()); filePick.addEventListener('change',()=>{send(filePick.files);filePick.value='';}); cameraPick.addEventListener('change',()=>{send(cameraPick.files);cameraPick.value='';});
"""
    new="""function makePayload(files){
 const fd=new FormData(); const csrf=form.querySelector('input[name="csrf_token"]');
 if(csrf)fd.append('csrf_token',csrf.value); files.forEach(f=>fd.append('files',f,f.name)); return fd;
}
function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms));}
async function uploadOnce(files){
 const ctrl=new AbortController(); const timeout=setTimeout(()=>ctrl.abort(),180000);
 try{
  return await fetch('/autopilot/upload',{method:'POST',body:makePayload(files),credentials:'same-origin',cache:'no-store',signal:ctrl.signal,headers:{'X-Requested-With':'XMLHttpRequest','X-BodyMind-Autopilot':'r7-mobile'}});
 }finally{clearTimeout(timeout);}
}
async function send(files){
 files=Array.from(files||[]).filter(Boolean); if(!files.length||busy)return;
 const max={{max_upload_mb|int}}*1024*1024, over=files.find(f=>f.size>max); if(over){msg('File troppo grande: '+over.name+'. Limite {{max_upload_mb|int}} MB.','err');return;}
 setBusy(true); results.innerHTML=''; msg('Analizzo '+files.length+' file…','busy');
 timers=[setTimeout(()=>busy&&msg('Leggo il documento e cerco l’atleta…','busy'),2200),setTimeout(()=>busy&&msg('OCR in corso…','busy'),6000),setTimeout(()=>busy&&msg('Aggiorno associazione e scadenza…','busy'),12000)];
 try{
  let r=null, lastErr=null;
  for(let attempt=1;attempt<=3;attempt++){
   try{r=await uploadOnce(files);lastErr=null;break;}
   catch(e){
    lastErr=e;
    if(e&&e.name==='AbortError')throw new Error('Il server ha impiegato troppo tempo. Riprova: il file non viene duplicato automaticamente.');
    if(attempt<3){msg('Connessione interrotta. Riprovo automaticamente… ('+attempt+'/2)','busy');await sleep(attempt===1?700:1600);}
   }
  }
  if(!r)throw(lastErr||new Error('Connessione al server non disponibile'));
  const txt=await r.text(); let data; try{data=JSON.parse(txt)}catch(_){data={ok:false,error:'Risposta server non valida (HTTP '+r.status+')'};}
  clearTimers(); setBusy(false); render(data||{});
  if(!r.ok||!data||data.ok===false){msg((data&&data.error)||'Import non riuscito. Puoi riprovare subito.','err');return;}
  const parts=[]; if(data.associati)parts.push(data.associati+' associati'); if(data.certificati_aggiornati)parts.push(data.certificati_aggiornati+' certificati aggiornati'); if(data.conferma)parts.push(data.conferma+' da confermare'); if(data.verificare)parts.push(data.verificare+' da verificare'); if(data.rifiutati)parts.push(data.rifiutati+' non importati'); if(data.elapsed_ms)parts.push((data.elapsed_ms/1000).toFixed(1)+' s');
  msg(parts.join(' · ')||'Import completato','ok');
 }catch(e){
  clearTimers();setBusy(false);
  const net=(e&&e.message)?e.message:'Connessione interrotta';
  msg('Import non completato. Controlla la connessione e riprova senza ricaricare la pagina.','err');
  results.innerHTML='<div class="errors">'+esc(net)+'</div>';
 }
}
form.addEventListener('submit',ev=>{ev.preventDefault();return false;});
fileBtn.addEventListener('click',()=>!busy&&filePick.click()); cameraBtn.addEventListener('click',()=>!busy&&cameraPick.click()); filePick.addEventListener('change',()=>{const chosen=Array.from(filePick.files||[]);filePick.value='';send(chosen);}); cameraPick.addEventListener('change',()=>{const chosen=Array.from(cameraPick.files||[]);cameraPick.value='';send(chosen);});
"""
    if new not in s:
        if old not in s:
            raise RuntimeError('R7 upload JS anchor missing')
        backup(rel)
        s=s.replace(old,new,1)
        p.write_text(s,encoding='utf-8')

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R7 compile failed')

    live=p.read_text(encoding='utf-8')
    required=[
        "form.addEventListener('submit',ev=>{ev.preventDefault()",
        "attempt<=3",
        "credentials:'same-origin'",
        "cache:'no-store'",
        "AbortController",
        "Connessione interrotta. Riprovo automaticamente",
        "X-BodyMind-Autopilot':'r7-mobile",
    ]
    missing=[x for x in required if x not in live]
    if missing:
        raise RuntimeError('R7 selftest missing: '+repr(missing))
    MARKER.write_text('BodyMind Autopilot R7 upload resilience applied\n',encoding='utf-8')
    print('[autopilot-r7] applied',flush=True)
    print('[autopilot-r7-selftest] PASS prevent-submit retry=3 timeout=180s no-store credentials=same-origin friendly-network-error',flush=True)
else:
    print('[autopilot-r7] already applied',flush=True)
