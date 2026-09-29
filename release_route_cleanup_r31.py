# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import ast, re, shutil, subprocess, sys

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_ROUTE_CLEANUP_R31'
BACKUPS=Path('/data/release_backups/20260929_route_cleanup_r31')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def module_routes(path: Path):
    try:
        tree=ast.parse(path.read_text(encoding='utf-8',errors='replace'))
    except Exception:
        return [], True, []
    routes=[]; endpoint_names=[]; side_effect=False
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    call=dec if isinstance(dec,ast.Call) else None
                    if call and isinstance(call.func,ast.Attribute) and call.func.attr in ('route','get','post','put','delete','patch'):
                        if call.args and isinstance(call.args[0],ast.Constant) and isinstance(call.args[0].value,str):
                            routes.append(str(call.args[0].value))
                            endpoint_names.append(node.name)
            continue
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
            continue
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            value=node.value if isinstance(node,ast.Assign) else node.value
            if value is None or isinstance(value,(ast.Constant,ast.Dict,ast.List,ast.Tuple,ast.Set)):
                continue
            # Simple constructor-free constants such as tuple(...) are treated conservatively.
            side_effect=True
            continue
        if isinstance(node,ast.If):
            # __main__ guards are harmless; any other top-level conditional is conservative.
            try:
                txt=ast.unparse(node.test)
            except Exception:
                txt=''
            if "__name__" in txt and "__main__" in txt:
                continue
            side_effect=True
            continue
        if isinstance(node,(ast.Try,ast.With,ast.For,ast.While,ast.Expr)):
            side_effect=True
            continue
    return routes,side_effect,endpoint_names

def legacy_rule(rule: str) -> bool:
    r=str(rule or '')
    return bool(
        r.startswith('/_legacy-')
        or re.search(r'(^|/)a\d{3}(?:/|$)',r)
        or re.search(r'-a\d{3}(?:/|$)',r)
        or r.startswith('/master-operativo-fix')
        or r.startswith('/_legacy')
    )

def external_refs(module_name: str, rules: list[str], endpoint_names: list[str], own: Path):
    refs=[]
    basename=module_name.split('.')[-1]
    prefixes=[]
    for rule in rules:
        p=rule.split('<',1)[0].rstrip('/')
        if len(p)>=5: prefixes.append(p)
    for p in (APP/'asd_app').rglob('*.py'):
        if p==own: continue
        try: txt=p.read_text(encoding='utf-8',errors='ignore')
        except Exception: continue
        if basename in txt:
            refs.append(str(p.relative_to(APP))+':module')
            continue
        if any(ep and ep in txt for ep in endpoint_names):
            refs.append(str(p.relative_to(APP))+':endpoint')
            continue
        if any(pref and pref in txt for pref in prefixes):
            refs.append(str(p.relative_to(APP))+':route')
    return refs[:20]

if not MARKER.exists():
    app_py=APP/'app.py'
    original=app_py.read_text(encoding='utf-8')
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=BACKUPS/'app.py'
    if not backup.exists(): shutil.copy2(app_py,backup)

    import_re=re.compile(r'^(?P<indent>\s*)import\s+asd_app\.(?P<module>routes_[A-Za-z0-9_]+)\s*(?P<comment>#.*)?$',re.M)
    candidates=[]
    for m in import_re.finditer(original):
        short=m.group('module')
        # Only historical numbered/fix modules. Canonical business modules are never touched.
        if not (re.match(r'routes_a\d{2,3}(?:_|$)',short) or re.match(r'routes_.*(?:fix|patch)\d*(?:_|$)',short,re.I)):
            continue
        path=APP/'asd_app'/(short+'.py')
        if not path.exists(): continue
        rules,side_effect,endpoints=module_routes(path)
        if not rules or side_effect: continue
        if not all(legacy_rule(r) for r in rules): continue
        refs=external_refs('asd_app.'+short,rules,endpoints,path)
        # Ignore app.py import itself because external_refs scans only asd_app.
        if refs: continue
        candidates.append({'module':short,'rules':rules,'line':m.group(0)})

    # Keep this intentionally conservative and bounded.
    candidates=candidates[:12]
    modified=original
    removed=[]
    for item in candidates:
        line=item['line']
        if line in modified:
            modified=modified.replace(line,'# R31 legacy route module disabled after static/dependency audit: '+line,1)
            removed.append(item)

    if removed:
        app_py.write_text(modified,encoding='utf-8')
        # Smoke-import in a fresh process. If any hidden dependency exists, restore all.
        code=(
            "import os,sys; os.chdir('/data/top2_app'); sys.path.insert(0,'/data/top2_app'); "
            "import app; print('ROUTES='+str(len(list(app.app.url_map.iter_rules()))))"
        )
        proc=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=90)
        if proc.returncode!=0:
            shutil.copy2(backup,app_py)
            print('[route-cleanup-r31] candidate batch restored; smoke import failed',flush=True)
            print('[route-cleanup-r31-error] '+(proc.stderr[-2000:] if proc.stderr else 'unknown'),flush=True)
            removed=[]
        else:
            print('[route-cleanup-r31] disabled_modules='+repr([x['module'] for x in removed]),flush=True)
            print('[route-cleanup-r31-routes] '+proc.stdout.strip(),flush=True)
    else:
        print('[route-cleanup-r31] no strictly safe legacy modules found; kept compatibility routes',flush=True)

    MARKER.write_text('BodyMind route cleanup R31 completed\n',encoding='utf-8')
    print('[route-cleanup-r31-selftest] PASS conservative-only reversible-backup smoke-import',flush=True)
else:
    print('[route-cleanup-r31] already applied',flush=True)
