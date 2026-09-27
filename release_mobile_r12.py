from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
TARGET=APP/'asd_app/routes_bodymind_fix22.py'
MARKER=APP/'.BODYMIND_MOBILE_SIMPLIFY_R12'
BACKUP=Path('/data/release_backups/20260927_mobile_r12/routes_bodymind_fix22.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not TARGET.exists():
    raise SystemExit('R12 mobile target missing')

if not MARKER.exists():
    src=TARGET.read_text(encoding='utf-8')
    if not BACKUP.exists():
        BACKUP.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(TARGET,BACKUP)

    old_sql='''docs = conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE lower(COALESCE(status,'')) NOT IN ('archived_to_tesserato','accepted','resolved')").fetchone()[0]'''
    new_sql='''docs = conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE lower(COALESCE(status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending') AND COALESCE(deleted_at,'')=''").fetchone()[0]'''
    if old_sql not in src:
        raise RuntimeError('R12 old mobile document counter anchor missing')
    src=src.replace(old_sql,new_sql,1)

    # In the dedicated mobile shell, "Documenti" means work to do now.
    src=src.replace('href="/documenti"', 'href="/documenti/da-verificare"')
    src=src.replace('<span>▤</span>Documenti</a>', '<span>▤</span>Verifiche</a>')

    # Make the primary alert wording explicit and action-oriented.
    src=src.replace('<small>Documenti da verificare</small>', '<small>{{\'Apri i documenti che richiedono conferma\' if docs else \'Nessun documento da verificare\'}}</small>',1)

    if "href=\"/documenti/da-verificare\"" not in src:
        raise RuntimeError('R12 queue link selftest failed')
    if "needs_manual_match" not in src or "associato_tipo_da_verificare" not in src or "richiede_conferma" not in src:
        raise RuntimeError('R12 real pending counter selftest failed')

    TARGET.write_text(src,encoding='utf-8')
    if not compileall.compile_file(str(TARGET),quiet=1):
        shutil.copy2(BACKUP,TARGET)
        raise RuntimeError('R12 compile failed; restored backup')

    MARKER.write_text('BodyMind mobile simplification R12 applied\n',encoding='utf-8')
    print('[mobile-r12] applied',flush=True)
    print('[mobile-r12-selftest] PASS real-pending-count direct-review-queue simplified-mobile-document-nav',flush=True)
else:
    print('[mobile-r12] already applied',flush=True)
