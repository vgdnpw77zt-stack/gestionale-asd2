# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3
from datetime import date, datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r82_guardian')
BACK.mkdir(parents=True,exist_ok=True)
MARKER=APP/'.BODYMIND_R82_GUARDIAN_CONVERGENCE'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r82.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

def iso(v):
    raw=str(v or '').strip()[:10]
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y'):
        try:return datetime.strptime(raw,fmt).date().isoformat()
        except Exception:pass
    return ''

def age(v):
    d=iso(v)
    if not d:return None
    born=date.fromisoformat(d); today=date.today()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day))

if not MARKER.exists():
    backup=backup_db()
    conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
    repaired=[]; created_minor=[]; remaining=[]
    try:
        from asd_app.verified_mu_sync_core_r68 import sync_guardian_bidirectional, _ensure_minor
        rows=conn.execute('SELECT * FROM tesserati ORDER BY id').fetchall()
        for a in rows:
            ks=set(a.keys()); tid=int(a['id'])
            aa=age(a['data_nascita'] if 'data_nascita' in ks else '')
            is_minor=(int(a['minorenne'] or 0)==1 if 'minorenne' in ks else False) or (aa is not None and aa<18)
            if not is_minor: continue

            result=sync_guardian_bidirectional(conn,tid)
            if result.get('profile_filled') or result.get('minor_filled'):
                repaired.append({'tid':tid,'phase':'bidirectional','result':result})

            # If profile already has guardian but minori row is missing, create only the structural row.
            fresh=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
            fks=set(fresh.keys())
            guard=''
            for k in ('genitore','nome_genitore'):
                if k in fks and fresh[k]:
                    guard=str(fresh[k]).strip()
                    if guard:break
            phone=str(fresh['telefono_genitore'] or '').strip() if 'telefono_genitore' in fks else ''
            email=str(fresh['email_genitore'] or '').strip() if 'email_genitore' in fks else ''
            mrow=conn.execute('SELECT * FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
            if not mrow and guard:
                analysis={
                  'first_name':str(fresh['nome'] or '') if 'nome' in fks else '',
                  'last_name':str(fresh['cognome'] or '') if 'cognome' in fks else '',
                  'birth_date':str(fresh['data_nascita'] or '') if 'data_nascita' in fks else '',
                  'guardian_name':guard,'guardian_phone':phone,'guardian_email':email,
                }
                mid,changed=_ensure_minor(conn,tid,fresh,analysis)
                if mid:
                    created_minor.append({'tid':tid,'minor_id':mid,'fields':sorted(changed.keys())})
                    result2=sync_guardian_bidirectional(conn,tid)
                    if result2.get('profile_filled') or result2.get('minor_filled'):
                        repaired.append({'tid':tid,'phase':'post_create','result':result2})

            # Final truth across both tables.
            fresh=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
            mrow=conn.execute('SELECT * FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
            def first(row,names):
                if not row:return ''
                rk=set(row.keys())
                for k in names:
                    if k in rk and row[k] is not None and str(row[k]).strip():
                        return str(row[k]).strip()
                return ''
            guardian=first(fresh,('genitore','nome_genitore')) or first(mrow,('genitore','nome_genitore'))
            gphone=first(fresh,('telefono_genitore','guardian_phone')) or first(mrow,('telefono_genitore','guardian_phone'))
            if not guardian or not gphone:
                remaining.append({
                  'tid':tid,'name':(str(fresh['nome'] or '')+' '+str(fresh['cognome'] or '')).strip(),
                  'guardian':guardian,'phone':gphone,
                  'has_minor_row':bool(mrow)
                })

        conn.commit()
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        tess=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
        minors=int(conn.execute('SELECT COUNT(*) FROM minori').fetchone()[0])
    finally:
        conn.close()

    print('[r82-guardian] repaired='+json.dumps(repaired,ensure_ascii=False)+
          ' created_minor='+json.dumps(created_minor,ensure_ascii=False)+
          ' remaining_real_missing='+json.dumps(remaining,ensure_ascii=False)+
          ' backup='+backup+' tesserati='+str(tess)+' minori='+str(minors)+
          ' integrity='+integrity+' fk='+str(fk),flush=True)
    if tess!=32 or integrity.lower()!='ok' or fk:
        raise RuntimeError('R82 guardian convergence guard failed')
    MARKER.write_text('BodyMind R82 guardian convergence applied\n',encoding='utf-8')
    print('[r82-selftest] PASS guardian-bidirectional minor-structure empty-only db-ok',flush=True)
else:
    print('[r82-guardian] already applied',flush=True)
