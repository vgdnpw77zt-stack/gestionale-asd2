from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_QUEUE_INTEGRITY_R15'
BACKUPS=Path('/data/release_backups/20260927_queue_integrity_r15')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    rel='asd_app/routes_a202_operational_integrity.py'
    p=APP/rel
    if not p.exists(): raise RuntimeError('R15 target missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R15_QUEUE_INTEGRITY' not in s:
        backup(rel)
        if 'from pathlib import Path' not in s:
            # Insert after the future import if available; otherwise at top.
            if 'from __future__ import annotations\n' in s:
                s=s.replace('from __future__ import annotations\n','from __future__ import annotations\nfrom pathlib import Path\n',1)
            else:
                s='from pathlib import Path\n'+s

        old_join="""LEFT JOIN tesserati t ON t.id=COALESCE(i.tesserato_id,i.matched_tesserato_id,i.suggested_tesserato_id)"""
        new_join="""LEFT JOIN tesserati t ON t.id=COALESCE(i.tesserato_id,i.matched_tesserato_id)"""
        if old_join not in s:
            raise RuntimeError('R15 assigned-athlete join anchor missing')
        s=s.replace(old_join,new_join,1)

        old_vars="""        did=int(r['id'])
        status=str(r['status'] or '')
        dtype=_r13_canonical_type(r['document_type'] or 'altro')
        dconf=int(r['document_confidence'] or 0)
        mscore=int(r['match_score'] or 0)
        tid=int(r['tesserato_id'] or 0)
"""
        new_vars="""        did=int(r['id'])
        status=str(r['status'] or '')
        dtype=_r13_canonical_type(r['document_type'] or 'altro')
        dconf=int(r['document_confidence'] or 0)
        mscore=int(r['match_score'] or 0)
        tid=int(r['tesserato_id'] or 0)
        saved_path=str(r['saved_path'] or '') if 'saved_path' in r.keys() else ''
        file_ok=bool(saved_path and Path(saved_path).is_file())  # BODYMIND_R15_QUEUE_INTEGRITY
"""
        if old_vars not in s:
            raise RuntimeError('R15 card vars anchor missing')
        s=s.replace(old_vars,new_vars,1)

        old_reason="""        if status=='needs_manual_match':
            reason='Identità atleta da assegnare'
        elif status=='associato_tipo_da_verificare':
            reason='Tipo documento da confermare'
        else:
            reason='Conferma richiesta'
"""
        new_reason="""        if not file_ok:
            reason='File non disponibile'
        elif status=='needs_manual_match':
            reason='Identità atleta da assegnare'
        elif status=='associato_tipo_da_verificare':
            reason='Tipo documento da confermare'
        else:
            reason='Conferma richiesta'
"""
        if old_reason not in s:
            raise RuntimeError('R15 reason anchor missing')
        s=s.replace(old_reason,new_reason,1)

        old_identity="""        identity=f"<b>{e(athlete)}</b><small>identità {mscore}%</small>" if athlete else "<b>Non assegnata</b><small>serve una scelta</small>"
"""
        new_identity="""        identity=f"<b>{e(athlete)}</b><small>identità {mscore}%</small>" if athlete else "<b>Non assegnata</b><small>nessun match automatico sicuro</small>"
"""
        if old_identity not in s:
            raise RuntimeError('R15 identity anchor missing')
        s=s.replace(old_identity,new_identity,1)

        old_assign='''        assign = ''
        if not tid:
            assign=f"""<form method='post' action='/documenti/da-verificare/{did}/atleta' class='r11-inline'>{csrf_input()}<select name='tesserato_id' required>{athlete_options}</select><button class='r11-btn' type='submit'>Assegna atleta</button></form>"""
'''
        new_assign='''        assign = ''
        if not tid and file_ok:
            assign=f"""<form method='post' action='/documenti/da-verificare/{did}/atleta' class='r11-inline'>{csrf_input()}<select name='tesserato_id' required>{athlete_options}</select><button class='r11-btn' type='submit'>Assegna atleta</button></form>"""
'''
        if old_assign not in s:
            raise RuntimeError('R15 assign anchor missing')
        s=s.replace(old_assign,new_assign,1)

        old_type='''        type_form=f"""<form method='post' action='/documenti/da-verificare/{did}/tipo' class='r11-inline'>{csrf_input()}<select name='document_type'>{options}</select><button class='r11-btn ghost' type='submit'>Correggi tipo</button></form>"""
'''
        new_type='''        type_form=(f"""<form method='post' action='/documenti/da-verificare/{did}/tipo' class='r11-inline'>{csrf_input()}<select name='document_type'>{options}</select><button class='r11-btn ghost' type='submit'>Correggi tipo</button></form>""" if file_ok else '')
'''
        if old_type not in s:
            raise RuntimeError('R15 type anchor missing')
        s=s.replace(old_type,new_type,1)

        old_open="""            <a class='r11-btn primary' target='_blank' rel='noopener' href='/documenti-automatici/file/{did}'>Apri</a>
            {ok}{dossier}{remove_form}
"""
        new_open="""            {f"<a class='r11-btn primary' target='_blank' rel='noopener' href='/documenti-automatici/file/{did}'>Apri</a>" if file_ok else "<span class='r11-missing'>File non disponibile sul volume</span>"}
            {ok if file_ok else ''}{dossier}{remove_form}
"""
        if old_open not in s:
            raise RuntimeError('R15 open anchor missing')
        s=s.replace(old_open,new_open,1)

        css_anchor=".r11-btn.danger{background:#3b1620;border-color:#7f1d1d;color:#fecaca!important}"
        css_new=css_anchor+".r11-missing{display:inline-flex;align-items:center;min-height:42px;padding:8px 12px;border-radius:12px;background:rgba(127,29,29,.22);border:1px solid rgba(248,113,113,.35);color:#fecaca;font-size:12px;font-weight:900}"
        if css_anchor not in s:
            raise RuntimeError('R15 CSS anchor missing')
        s=s.replace(css_anchor,css_new,1)

        p.write_text(s,encoding='utf-8')
        if not compileall.compile_file(str(p),quiet=1):
            raise RuntimeError('R15 compile failed')
    MARKER.write_text('BodyMind queue integrity R15 applied\n',encoding='utf-8')
    print('[queue-r15] applied',flush=True)
    print('[queue-r15-selftest] PASS assigned-only-identity file-state no-broken-open removable-orphan',flush=True)
else:
    print('[queue-r15] already applied',flush=True)
