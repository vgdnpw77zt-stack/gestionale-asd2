"""A262: exact-anchor patch for A253/A261 staging source. No Railway operations."""
from pathlib import Path
import hashlib
import json

SOURCE=Path(__file__).parent/'source'

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def apply(root):
    root=Path(root)
    original=root/'bodymind_a237_finance_truth.py'
    dashboard=root/'routes_dashboard.py'
    if not original.is_file() or not dashboard.is_file():raise RuntimeError('STOP: sources missing')
    src=original.read_text(encoding='utf-8');dash=dashboard.read_text(encoding='utf-8')
    if 'A262_ORIGIN_ACTIVE' in src:
        raise RuntimeError('STOP: already applied; use verification only')
    if 'A261 advanced controls toggle' not in dash or 'A260 accessible quick overview' not in dash:
        raise RuntimeError('STOP: A261 UI not found')
    exact="        return {\n            **by_channel,\n            'entrate':income,'uscite':outgoing,'saldo':income-outgoing,"
    replacement="""        # A262_ORIGIN_ACTIVE: counts derive from the SAME validated A237 rows.
        from . import bodymind_a262_income_origin as _a262
        origins=_a262.build(c,ps,active_pids,manual_in,income,
                             by_channel['entrate_per_metodo'],live_count)
        return {
            **by_channel,
            'origini_entrate':origins,
            'entrate':income,'uscite':outgoing,'saldo':income-outgoing,"""
    if src.count(exact)!=1:raise RuntimeError('STOP: A237 finance snapshot changed')
    src=src.replace(exact,replacement,1)
    exact2="    partition=''.join('<div class=\"bm-method\""
    if src.count(exact2)!=1:raise RuntimeError('STOP: method partition anchor changed')
    src=src.replace(exact2,"    from . import bodymind_a262_income_origin as _a262\n    origin_markup=_a262.css()+_a262.render(data['origini_entrate'])\n"+exact2,1)
    exact3="<div class=\"method-grid\">'''+partition+'''</div>"
    if src.count(exact3)!=1:raise RuntimeError('STOP: finance panel anchor changed')
    src=src.replace(exact3,exact3+"'''+origin_markup+'''",1)
    old='def inject_dashboard(doc, data):\n    return inject_markup(doc,finance_panel(data))'
    newer='''def inject_dashboard(doc, data):
    from . import bodymind_a262_income_origin as _a262
    doc,changed=inject_markup(doc,finance_panel(data))
    if 'A261 advanced controls toggle:' not in doc or 'a260-state-grid' not in doc:
        return doc,changed
    anchor="      </section>\\n\\n      <!-- A261 advanced controls toggle:"
    if doc.count(anchor)!=1:
        raise ValueError('STOP: dashboard A261 insertion anchor missing/ambiguous')
    teaser=_a262.css()+_a262.tiny(data['origini_entrate'])
    nav="""<script id='a262-origin-navigation'>
    document.addEventListener('click',function(event){
      var link=event.target.closest('#a262-show-details');
      if(!link)return;
      var box=document.querySelector('.pro-dashboard.a261-compact');
      if(box){var btn=box.querySelector('#a261-more-button');if(btn)btn.click();}
    },true);</script>"""
    doc=doc.replace(anchor,teaser+"\\n      </section>\\n\\n      <!-- A261 advanced controls toggle:",1)
    pos=doc.lower().rfind('</body>')
    doc=doc[:pos]+nav+doc[pos:] if pos>=0 else doc+nav
    return doc,True'''
    if src.count(old)!=1:raise RuntimeError('STOP: inject_dashboard anchor changed')
    src=src.replace(old,newer,1)
    compile(src,str(original),'exec')
    helper=SOURCE/'bodymind_a262_income_origin.py'
    if not helper.is_file():raise RuntimeError('STOP: helper missing')
    if (root/'bodymind_a262_income_origin.py').exists():raise RuntimeError('STOP: helper collision')
    # Write to isolated staging copy only, after all checks; never directly /data.
    original.write_text(src,encoding='utf-8')
    (root/'bodymind_a262_income_origin.py').write_bytes(helper.read_bytes())
    return {'files':{str(original.name):digest(src),str(helper.name):hashlib.sha256(helper.read_bytes()).hexdigest()},'dashboard_sha_unchanged':digest(dash)}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--root',required=True)
 args=p.parse_args();print(json.dumps(apply(args.root),indent=2))
