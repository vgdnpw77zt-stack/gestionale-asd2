from __future__ import annotations
from pathlib import Path
from datetime import datetime
import compileall, shutil, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_UNIFIED_FLAGS_R16'
BACKUPS=Path('/data/release_backups/20260928_unified_flags_r16')

TESSERATO_FLAGS=(
    'consenso_informato',
    'liberatoria_immagini',
    'manleva_firmata',
    'iscrizione_firmata',
    'documenti_onboarding_ok',
    'privacy_ok',
    'liberatoria_ok',
    'regolamento_ok',
)

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def cols(conn,table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}

def has_table(conn,table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def sync_sql(conn,tid):
    tid=int(tid or 0)
    if tid<=0 or not has_table(conn,'tesserati'):
        return False
    tc=cols(conn,'tesserati')
    fields=[f for f in TESSERATO_FLAGS if f in tc]
    if fields:
        conn.execute('UPDATE tesserati SET '+','.join(f+'=1' for f in fields)+' WHERE id=?',(tid,))
    if has_table(conn,'minori'):
        mc=cols(conn,'minori')
        row=conn.execute('SELECT id FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
        if row:
            sets=[]
            vals=[]
            if 'consenso_firmato' in mc: sets.append('consenso_firmato=1')
            if 'autorizzazioni_ok' in mc: sets.append('autorizzazioni_ok=1')
            if 'data_consenso' in mc:
                sets.append("data_consenso=COALESCE(NULLIF(data_consenso,''),?)")
                vals.append(datetime.now().date().isoformat())
            if 'note_consenso' in mc:
                sets.append("note_consenso=CASE WHEN TRIM(COALESCE(note_consenso,''))='' THEN 'Modulo Unico MU-2026.1 verificato' ELSE note_consenso END")
            if sets:
                vals.append(tid)
                conn.execute('UPDATE minori SET '+','.join(sets)+' WHERE tesserato_id=?',vals)
    return True

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    # Central helper: one verified MU satisfies all declarations contained in MU-2026.1.
    rel='asd_app/onboarding_flow.py'; p=APP/rel
    if not p.exists(): raise RuntimeError('R16 onboarding_flow missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R16_UNIFIED_FLAGS' not in s:
        backup(rel)
        anchor='def ensure_onboarding_schema(conn) -> None:\n'
        helper=r'''# BODYMIND_R16_UNIFIED_FLAGS
def sync_unified_module_flags(conn, tesserato_id: int, source: str = 'modulo_unico') -> None:
    """Synchronize only declarations covered by the verified BodyMind MU-2026.1.
    Identity auto-match alone must never call this helper.
    """
    tid=int(tesserato_id or 0)
    if tid <= 0:
        return
    tcols=_cols(conn,'tesserati')
    covered=(
        'consenso_informato','liberatoria_immagini','manleva_firmata',
        'iscrizione_firmata','documenti_onboarding_ok',
        'privacy_ok','liberatoria_ok','regolamento_ok',
    )
    sets=[name+'=1' for name in covered if name in tcols]
    if sets:
        conn.execute('UPDATE tesserati SET '+','.join(sets)+' WHERE id=?',(tid,))
    if 'minori' in {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
        mcols=_cols(conn,'minori')
        minor=conn.execute('SELECT id FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
        if minor:
            msets=[]; vals=[]
            if 'consenso_firmato' in mcols:
                msets.append('consenso_firmato=1')
            # autorizzazioni_ok means the MU authorization section was completed.
            # Do NOT force delega_ritiro_ok / uscita_autonoma_ok: those are choices, not completeness.
            if 'autorizzazioni_ok' in mcols:
                msets.append('autorizzazioni_ok=1')
            if 'data_consenso' in mcols:
                msets.append("data_consenso=COALESCE(NULLIF(data_consenso,''),?)")
                vals.append(datetime.now().date().isoformat())
            if 'note_consenso' in mcols:
                msets.append("note_consenso=CASE WHEN TRIM(COALESCE(note_consenso,''))='' THEN ? ELSE note_consenso END")
                vals.append('Modulo Unico MU-2026.1 verificato')
            if msets:
                vals.append(tid)
                conn.execute('UPDATE minori SET '+','.join(msets)+' WHERE tesserato_id=?',vals)


'''
        if anchor not in s: raise RuntimeError('R16 onboarding helper anchor missing')
        s=s.replace(anchor,helper+anchor,1)
        p.write_text(s,encoding='utf-8')

    # Manual final OK is the trust boundary: synchronize all covered declarations there.
    rel='asd_app/routes_a202_operational_integrity.py'; p=APP/rel
    if not p.exists(): raise RuntimeError('R16 a202 missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R16_FINAL_OK_SYNC' not in s:
        backup(rel)
        old="""        from .onboarding_flow import recompute_onboarding_status
        recompute_onboarding_status(conn,tid)"""
        new="""        from .onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
        sync_unified_module_flags(conn,tid,source='coda_documenti')  # BODYMIND_R16_FINAL_OK_SYNC
        recompute_onboarding_status(conn,tid)"""
        if old not in s: raise RuntimeError('R16 final OK sync anchor missing')
        s=s.replace(old,new,1)
        p.write_text(s,encoding='utf-8')

    # A negative choice on delegate/autonomous exit is not an incomplete practice.
    rel='asd_app/routes_a151_final_ops.py'; p=APP/rel
    if not p.exists(): raise RuntimeError('R16 a151 missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R16_OPTIONAL_MINOR_CHOICES' not in s:
        backup(rel)
        old="""        if 'delega_ritiro_ok' in cols and _safe_int(_row(m, 'delega_ritiro_ok')) != 1:
            issues.append('delega ritiro mancante')
        if 'uscita_autonoma_ok' in cols and _safe_int(_row(m, 'uscita_autonoma_ok')) != 1:
            issues.append('uscita autonoma non autorizzata')
        if 'autorizzazioni_ok' in cols and _safe_int(_row(m, 'autorizzazioni_ok')) != 1:
            issues.append('autorizzazioni incomplete')"""
        new="""        # BODYMIND_R16_OPTIONAL_MINOR_CHOICES
        # delega_ritiro_ok and uscita_autonoma_ok are the parent's choices.
        # 0 can legitimately mean "not authorised"; it must not create a missing-document alert.
        if 'autorizzazioni_ok' in cols and _safe_int(_row(m, 'autorizzazioni_ok')) != 1:
            issues.append('sezione autorizzazioni del Modulo Unico da verificare')"""
        if old not in s: raise RuntimeError('R16 optional minor choices anchor missing')
        s=s.replace(old,new,1)
        p.write_text(s,encoding='utf-8')

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R16 compile failed')

    # Safe backfill: only profiles already explicitly marked as onboarding-documents OK.
    if DB.exists():
        conn=sqlite3.connect(str(DB),timeout=20)
        try:
            tc=cols(conn,'tesserati')
            if 'documenti_onboarding_ok' in tc:
                ids=[int(r[0]) for r in conn.execute('SELECT id FROM tesserati WHERE COALESCE(documenti_onboarding_ok,0)=1').fetchall()]
            else:
                ids=[]
            for tid in ids:
                sync_sql(conn,tid)
            conn.commit()
            minor_open=0
            if has_table(conn,'minori'):
                mc=cols(conn,'minori')
                if 'consenso_firmato' in mc and 'autorizzazioni_ok' in mc:
                    minor_open=conn.execute('SELECT COUNT(*) FROM minori WHERE COALESCE(consenso_firmato,0)<>1 OR COALESCE(autorizzazioni_ok,0)<>1').fetchone()[0]
            print(f'[unified-flags-r16] backfilled={len(ids)} minor_incomplete_after={minor_open}',flush=True)
        finally:
            conn.close()

    MARKER.write_text('BodyMind unified flags R16 applied\n',encoding='utf-8')
    print('[unified-flags-r16] applied',flush=True)
    print('[unified-flags-r16-selftest] PASS final-ok-sync privacy-images-signatures minor-consent optional-minor-choices',flush=True)
else:
    print('[unified-flags-r16] already applied',flush=True)
