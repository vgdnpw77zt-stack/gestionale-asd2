import inspect
TARGET_PREFIXES=('/mobile','/documenti','/document-hub','/documenti-automatici')
try:
    import app as entry
    flask_app=entry.app
    print('[mobile-probe] BEGIN',flush=True)
    for rule in list(flask_app.url_map.iter_rules()):
        path=str(rule.rule)
        if path.startswith(TARGET_PREFIXES):
            fn=flask_app.view_functions.get(rule.endpoint)
            try:
                src=inspect.getsourcefile(fn) or ''
                lines,lineno=inspect.getsourcelines(fn)
                excerpt=' || '.join(x.strip()[:700] for x in lines[:220])
            except Exception as exc:
                src='';lineno=0;excerpt='ERR '+repr(exc)
            print(f'[mobile-probe] RULE {path} endpoint={rule.endpoint} methods={sorted(rule.methods)} src={src} line={lineno}',flush=True)
            print(f'[mobile-probe] SOURCE {path} {excerpt}',flush=True)
    print('[mobile-probe] END',flush=True)
except Exception as exc:
    print('[mobile-probe] FATAL '+repr(exc),flush=True)
