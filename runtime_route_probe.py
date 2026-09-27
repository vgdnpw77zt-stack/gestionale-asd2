import inspect
TARGETS={'/','/document-hub','/documenti','/documenti-automatici','/firma-smart','/generatore-documenti','/cuore-operativo'}
try:
    import app as entry
    flask_app=entry.app
    print('[route-probe] BEGIN',flush=True)
    for rule in list(flask_app.url_map.iter_rules()):
        if str(rule.rule) in TARGETS:
            fn=flask_app.view_functions.get(rule.endpoint)
            try:
                src=inspect.getsourcefile(fn) or ''
                lines,lineno=inspect.getsourcelines(fn)
                excerpt=' || '.join(x.strip()[:500] for x in lines[:45])
            except Exception as exc:
                src=''; lineno=0; excerpt='ERR '+repr(exc)
            print(f'[route-probe] RULE {rule.rule} endpoint={rule.endpoint} methods={sorted(rule.methods)} src={src} line={lineno}',flush=True)
            print(f'[route-probe] SOURCE {rule.rule} {excerpt}',flush=True)
    try:
        from asd_app import core
        fn=core.layout
        src=inspect.getsourcefile(fn) or ''
        lines,lineno=inspect.getsourcelines(fn)
        keep=[]
        for off,line in enumerate(lines):
            low=line.lower()
            if any(k in low for k in ('sidebar','document','firma','generatore','nav-link','href=')):
                keep.append(f'{lineno+off}:{line.strip()[:700]}')
        print('[route-probe] LAYOUT '+src+' '+' || '.join(keep[:140]),flush=True)
    except Exception as exc:
        print('[route-probe] LAYOUTERR '+repr(exc),flush=True)
    print('[route-probe] END',flush=True)
except Exception as exc:
    print('[route-probe] FATAL '+repr(exc),flush=True)
