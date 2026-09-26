from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP = Path('/data/top2_app')
MARKER = APP / '.BODYMIND_AUTOPILOT_R7'
BACKUPS = Path('/data/release_backups/20260926_autopilot_r7')

def backup(rel: str):
    src = APP / rel
    dst = BACKUPS / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    rel = 'asd_app/routes_bodymind_fix49.py'
    p = APP / rel
    if not p.exists():
        raise RuntimeError('R7 target missing: '+rel)
    s = p.read_text(encoding='utf-8')

    marker = 'BODYMIND_R7_UPLOAD_RESILIENCE'
    if marker not in s:
        injection = r"""
/* BODYMIND_R7_UPLOAD_RESILIENCE
   Additive transport guard: do not replace Autopilot business logic.
   Prevent native form navigation and retry transient fetch/network failures.
*/
(function(){
  if(window.__bodymindR7UploadResilience) return;
  window.__bodymindR7UploadResilience = true;

  try {
    if(typeof form !== 'undefined' && form){
      form.addEventListener('submit', function(ev){
        ev.preventDefault();
        ev.stopPropagation();
        return false;
      }, true);
    }
  } catch(_e) {}

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function(input, init){
    let url = '';
    try { url = (typeof input === 'string') ? input : ((input && input.url) || ''); } catch(_e) {}
    if(url.indexOf('/autopilot/upload') === -1){
      return nativeFetch(input, init);
    }

    const opts = Object.assign({}, init || {}, {credentials:'same-origin', cache:'no-store'});
    let lastError = null;
    for(let attempt=1; attempt<=3; attempt++){
      try {
        return await nativeFetch(input, opts);
      } catch(err) {
        lastError = err;
        if(attempt < 3){
          try {
            if(typeof msg === 'function'){
              msg('Connessione interrotta. Riprovo automaticamente… ('+attempt+'/2)','busy');
            }
          } catch(_e) {}
          await new Promise(resolve => setTimeout(resolve, attempt === 1 ? 700 : 1600));
        }
      }
    }
    throw lastError || new Error('Connessione al server non disponibile');
  };
})();
"""
        pos = s.rfind('</script>')
        if pos < 0:
            raise RuntimeError('R7 script closing tag not found')
        backup(rel)
        s = s[:pos] + injection + '\n' + s[pos:]
        p.write_text(s, encoding='utf-8')

    if not compileall.compile_dir(str(APP / 'asd_app'), quiet=1):
        raise RuntimeError('Autopilot R7 compile failed')

    live = p.read_text(encoding='utf-8')
    required = [
        'BODYMIND_R7_UPLOAD_RESILIENCE',
        "url.indexOf('/autopilot/upload')",
        'attempt<=3',
        "credentials:'same-origin'",
        "cache:'no-store'",
        "form.addEventListener('submit'",
        'preventDefault',
        'Connessione interrotta. Riprovo automaticamente',
    ]
    missing = [x for x in required if x not in live]
    if missing:
        raise RuntimeError('R7 selftest missing: '+repr(missing))

    MARKER.write_text('BodyMind Autopilot R7 additive upload resilience applied\n', encoding='utf-8')
    print('[autopilot-r7] applied', flush=True)
    print('[autopilot-r7-selftest] PASS additive prevent-submit retry=3 no-store credentials=same-origin', flush=True)
else:
    print('[autopilot-r7] already applied', flush=True)
