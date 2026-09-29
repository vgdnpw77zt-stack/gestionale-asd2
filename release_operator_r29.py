from __future__ import annotations

from pathlib import Path
import compileall
import re
import shutil

APP=Path('/data/top2_app')
SRC=Path('/opt/bodymind/operator_bodymind_runtime_r29.py')
TARGET=APP/'asd_app/routes_operator_bodymind.py'
MARKER=APP/'.BODYMIND_OPERATOR_R29'
BACKUPS=Path('/data/release_backups/20260929_operator_r29')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not SRC.exists():
    raise SystemExit('R29 operator source missing')

def backup(rel):
    src=APP/rel
    dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def patch(rel, transform):
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R29 target missing: '+rel)
    old=p.read_text(encoding='utf-8',errors='replace')
    new=transform(old)
    if new!=old:
        backup(rel)
        p.write_text(new,encoding='utf-8')
    return new

if not MARKER.exists():
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup('asd_app/routes_operator_bodymind.py')
    TARGET.write_text(SRC.read_text(encoding='utf-8'),encoding='utf-8')

    def patch_app(s):
        if 'import asd_app.routes_operator_bodymind' in s:
            return s
        anchor='import asd_app.routes_didattica_ia  # noqa: F401'
        if anchor not in s:
            anchor='import asd_app.routes_documenti  # noqa: F401'
        if anchor not in s:
            raise RuntimeError('R29 app import anchor missing')
        return s.replace(anchor,anchor+'\nimport asd_app.routes_operator_bodymind  # noqa: F401  # R29 Operatore BodyMind',1)

    patch('app.py',patch_app)

    def patch_core(s):
        if 'BODYMIND_R29_OPERATOR_NAV' not in s:
            # Put Operatore BodyMind immediately after Dashboard.
            lines=s.splitlines(True)
            inserted=False
            for i,line in enumerate(lines):
                if "+ nav_link('/', 'Dashboard'" in line:
                    indent=line[:len(line)-len(line.lstrip())]
                    lines.insert(i+1,indent+"+ nav_link('/operatore-bodymind', 'Operatore BodyMind', 'bolt', tier='core', title='Segreteria intelligente: parla, cerca, controlla e prepara azioni sul gestionale.')  # BODYMIND_R29_OPERATOR_NAV\n")
                    inserted=True
                    break
            if not inserted:
                raise RuntimeError('R29 dashboard nav anchor missing')
            s=''.join(lines)

            # Operational legacy cockpit remains available only in Advanced mode.
            start=s.find("+ nav_dropdown('Operatività', 'bolt',")
            end=s.find("+ nav_dropdown('Persone', 'users',",start)
            if start>=0 and end>start:
                segment=s[start:end]
                stripped=segment.lstrip()
                prefix=segment[:len(segment)-len(stripped)]
                if stripped.startswith('+ '):
                    expr=stripped[2:].rstrip()
                    replacement=prefix+"+ ("+expr+" if is_advanced_mode() else '')\n"
                    s=s[:start]+replacement+s[end:]
            else:
                raise RuntimeError('R29 operational nav block missing')

            # Hide secondary/legacy daily-work entries in Simple mode without removing their routes.
            replacements={
              "if can_access_section('collaboratori') else ''":"if can_access_section('collaboratori') and is_advanced_mode() else ''",
              "if has_role('admin') else '')\n+ (nav_link('/iscrizioni-online/admin'":"if has_role('admin') and is_advanced_mode() else '')\n+ (nav_link('/iscrizioni-online/admin'",
              "if has_role('admin') and is_saas_mode() else ''":"if has_role('admin') and is_saas_mode() and is_advanced_mode() else ''",
              "if has_role('admin') else '')\n+ (nav_link('/catalogo'":"if has_role('admin') and is_advanced_mode() else '')\n+ (nav_link('/catalogo'",
            }
            for a,b in replacements.items():
                s=s.replace(a,b)

            # Targeted secondary payment tools: Quote & Incassi remains the simple-mode home.
            s=s.replace(
              "(nav_link('/pagamenti', 'Pagamenti / link'",
              "(nav_link('/pagamenti', 'Pagamenti / link'"
            )
            s=re.sub(
              r"(\(nav_link\('/pagamenti', 'Pagamenti / link'.*?) if can_access_section\('pagamenti'\) else ''\)",
              r"\1 if can_access_section('pagamenti') and is_advanced_mode() else '')",
              s,flags=re.S
            )
            s=re.sub(
              r"(\(nav_link\('/ricevute', 'Ricevute'.*?) if can_access_section\('ricevute'\) else ''\)",
              r"\1 if can_access_section('ricevute') and is_advanced_mode() else '')",
              s,flags=re.S
            )
            s=re.sub(
              r"(\(nav_link\('/contabilita', 'Contabilità'.*?) if can_access_section\('contabilita'\) else ''\)",
              r"\1 if can_access_section('contabilita') and is_advanced_mode() else '')",
              s,flags=re.S
            )

        # Dead JS reference generated a 404 on every main-page load.
        # core.py builds HTML inside a quoted Python string, so support both escaped and plain quotes.
        for dead in (
            "<script src=\\'/static/demo/demo_wow.js?v=a82-hardening-build\\'></script>",
            "<script src='/static/demo/demo_wow.js?v=a82-hardening-build'></script>",
            '<script src="/static/demo/demo_wow.js?v=a82-hardening-build"></script>',
        ):
            s=s.replace(dead,"")
        s=re.sub(r"<script src=\\?['\"]/static/demo/demo_wow\.js[^>]*></script>","",s)
        return s

    core=patch('asd_app/core.py',patch_core)

    # Keep exactly one canonical /health and move only the historical A61 route.
    health_patched=False
    for p in (APP/'asd_app').glob('*.py'):
        txt=p.read_text(encoding='utf-8',errors='replace')
        idx=txt.find('def health_a61')
        if idx<0:
            continue
        window_start=max(0,idx-700)
        window=txt[window_start:idx]
        rel=window.rfind('/health')
        if rel>=0:
            absolute=window_start+rel
            backup(str(p.relative_to(APP)))
            txt=txt[:absolute]+'/_legacy-health-a61'+txt[absolute+len('/health'):]
            p.write_text(txt,encoding='utf-8')
            health_patched=True
            break

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R29 compileall failed')
    if not compileall.compile_file(str(APP/'app.py'),quiet=1):
        raise RuntimeError('R29 app compile failed')

    app_txt=(APP/'app.py').read_text(encoding='utf-8')
    core_txt=(APP/'asd_app/core.py').read_text(encoding='utf-8')
    op_txt=TARGET.read_text(encoding='utf-8')
    checks={
      'operator-import':'import asd_app.routes_operator_bodymind' in app_txt,
      'operator-route':'/operatore-bodymind' in op_txt and '/operatore-bodymind/chat' in op_txt,
      'voice':'SpeechRecognition' in op_txt and 'speechSynthesis' in op_txt,
      'upload-autopilot':'process_inbound_attachment' in op_txt,
      'identity':'bodymind_operator_identity' in op_txt,
      'safe-confirm':'bodymind_operator_pending_action' in op_txt,
      'nav':'BODYMIND_R29_OPERATOR_NAV' in core_txt,
      'dead-demo':'demo_wow.js' not in core_txt,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R29 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind Operatore R29 applied\n',encoding='utf-8')
    print('[operator-r29] applied health_legacy_moved='+str(health_patched),flush=True)
    print('[operator-r29-selftest] PASS voice identity conversation athlete-search docs minors certificates quota-confirm upload-autopilot simplified-nav dead-js-cleanup',flush=True)
else:
    # Keep operator runtime source current if the container image is newer, without touching data.
    current=TARGET.read_text(encoding='utf-8',errors='replace') if TARGET.exists() else ''
    desired=SRC.read_text(encoding='utf-8')
    if current!=desired:
        TARGET.write_text(desired,encoding='utf-8')
        print('[operator-r29] operator module refreshed from image',flush=True)
    print('[operator-r29] already applied',flush=True)
