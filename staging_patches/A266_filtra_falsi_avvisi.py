"""BodyMind A266 STAGING: fix false payment alerts; keep safety warnings."""
from pathlib import Path
import os,hashlib,json,argparse

def patch(root):
 p=Path(root)/'core.py'
 text=p.read_text(encoding='utf-8')
 if 'BODYMIND_A266_TRUTHFUL_ALERT_FILTER' in text:return {'changed':False,'sha256':hashlib.sha256(text.encode()).hexdigest()}
 old='''            typ=str(alert.get('category') or '').lower()
            tid=int(alert.get('tesserato_id') or 0)
            member=byid.get(tid)'''
 new='''            # BODYMIND_A266_TRUTHFUL_ALERT_FILTER: the canonical alert ID lives in meta.
            typ=str(alert.get('category') or '').lower()
            meta=alert.get('meta') if isinstance(alert.get('meta'),dict) else {}
            tid=int(alert.get('tesserato_id') or meta.get('tesserato_id') or 0)
            member=byid.get(tid)'''
 if text.count(old)!=1:raise RuntimeError('STOP A266: cannot find unique A229 alert anchor')
 text=text.replace(old,new,1)
 old="        result['alerts']=revised\n    except Exception as exc:"
 new="""        result['alerts']=revised
        # A266: derived badges must be based on the *filtered* alerts.
        result['bloccanti']=sum(1 for a in revised if isinstance(a,dict) and
            isinstance(a.get('meta'),dict) and a['meta'].get('blocker'))
        result['oggi_bloccati']=len({str(a.get('meta',{}).get('tesserato_id'))
            for a in revised if isinstance(a,dict) and isinstance(a.get('meta'),dict)
            and a['meta'].get('blocker') and a['meta'].get('tesserato_id')})
        # The task list uses the same alert category/athlete truth; do not reopen paid fees.
        clean_tasks=[]
        for task in result.get('tasks',[]):
            if not isinstance(task,dict):clean_tasks.append(task);continue
            task_meta=task.get('meta') if isinstance(task.get('meta'),dict) else {}
            task_typ=str(task.get('category') or '').lower()
            task_tid=int(task.get('tesserato_id') or task_meta.get('tesserato_id') or 0)
            task_member=byid.get(task_tid)
            if task_member is not None and task_typ in ('pagamento','tesseramento'):
                task_status=task_member.get('mensile_stato' if task_typ=='pagamento' else 'iscrizione_stato')
                if task_status in ('pagato','non_dovuto','da_definire'):continue
            clean_tasks.append(task)
        result['tasks']=clean_tasks
        result['task_aperti']=sum(1 for t in clean_tasks if isinstance(t,dict) and t.get('status') in ('open','in_lavorazione','posticipato'))
    except Exception as exc:"""
 if text.count(old)!=1:raise RuntimeError('STOP A266: duplicate A229 result anchor')
 text=text.replace(old,new,1)
 old='''            for col, label in [("telefono","telefono"),("email","email"),("corso","corso"),("data_nascita","data nascita")]:
                if col in t_cols and not str(_row_get(t, col, "") or "").strip():
                    missing.append(label)'''
 new='''            for col, label in [("telefono","telefono"),("email","email"),("corso","corso"),("data_nascita","data nascita")]:
                if col == 'email' and str(_row_get(t,'telefono','') or '').strip():
                    continue  # BODYMIND_A266: one reachable contact channel suffices for this warning.
                if col == 'telefono' and str(_row_get(t,'email','') or '').strip():
                    continue
                if col in t_cols and not str(_row_get(t, col, "") or "").strip():
                    missing.append(label)'''
 if text.count(old)!=1:raise RuntimeError('STOP A266: contact alerts anchor not found')
 text=text.replace(old,new,1)
 compile(text,str(p),'exec')
 tmp=p.with_suffix('.a266-tmp');tmp.write_text(text,encoding='utf-8');os.replace(tmp,p)
 return {'changed':True,'sha256':hashlib.sha256(text.encode()).hexdigest()}

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--root',required=True);opt=a.parse_args()
 print(json.dumps(patch(opt.root),indent=2))
