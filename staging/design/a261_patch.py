"""A261: progressive-disclosure follow-up to BodyMind A260.

Works ONLY on a reviewed A260 source clone and never accesses the live DB.
Does not change payment, receipt, athlete or document handlers.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

CSS = r'''
/* A261: one lightweight work surface; advanced dashboard is always restorable. */
html body .pro-dashboard.a62-topfix-dashboard .a261-more-button {
 width:100%;min-height:46px;display:flex;align-items:center;justify-content:space-between;
 padding:10px 16px;margin:0 0 16px;border-radius:12px;border:1px solid #3d566c;
 color:#d7eaf6;background:#192c3d;box-shadow:none;font:700 13px/1.45 system-ui,sans-serif;cursor:pointer;
}
html body .pro-dashboard.a62-topfix-dashboard .a261-more-button:hover {background:#243c51;}
html body .pro-dashboard.a62-topfix-dashboard .a261-more-button:focus-visible {outline:3px solid #85c6ec;outline-offset:3px;}
html body .pro-dashboard.a62-topfix-dashboard .a261-more-button .a261-caret {font-size:15px;transition:transform .15s ease;}
html body .pro-dashboard.a62-topfix-dashboard.a261-compact > section:not(.a260-today) {display:none!important;}
html body .pro-dashboard.a62-topfix-dashboard.a261-compact > .a261-more-button .a261-caret {transform:rotate(0deg);}
html body .pro-dashboard.a62-topfix-dashboard:not(.a261-compact) > .a261-more-button .a261-caret {transform:rotate(180deg);}
@media(max-width:730px){
 html body .pro-dashboard.a62-topfix-dashboard .a261-more-button {margin-bottom:12px;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-today-head {margin-bottom:14px;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-today {box-shadow:none!important;}
}
@media(prefers-reduced-motion:reduce){html body .pro-dashboard.a62-topfix-dashboard .a261-caret {transition:none;}}
'''
BUTTON = '''
      <!-- A261 advanced controls toggle: all existing panels remain in the DOM. -->
      <button type='button' class='a261-more-button' id='a261-more-button' aria-expanded='true'>
         <span class='a261-toggle-text'>Mostra altri controlli</span><span class='a261-caret' aria-hidden='true'>⌄</span>
      </button>
'''
JS = r'''
    <script id="a261-progressive-dashboard">
    (() => {
      const root = document.querySelector('.pro-dashboard.a62-topfix-dashboard');
      const button = root && root.querySelector('#a261-more-button');
      if (!root || !button) return;
      const title = button.querySelector('.a261-toggle-text');
      const rememberKey = 'bodymind_dashboard_advanced_open_v1';
      // Default: compact. Preserve an explicit "show" choice for this browser tab only.
      let opened = false;
      try { opened = sessionStorage.getItem(rememberKey) === '1'; } catch (e) {}
      const apply = () => {
        root.classList.toggle('a261-compact', !opened);
        button.setAttribute('aria-expanded', String(opened));
        if (title) title.textContent = opened ? 'Nascondi altri controlli' : 'Mostra altri controlli';
      };
      apply();
      button.addEventListener('click', () => {
        opened = !opened;
        try { sessionStorage.setItem(rememberKey, opened ? '1' : '0'); } catch (e) {}
        apply();
      });
    })();
    </script>
'''

def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def patch(root: str | Path):
    root=Path(root)
    path=root/'routes_dashboard.py'
    original=path.read_text(encoding='utf-8')
    if 'A260 accessible quick overview' not in original:
        raise RuntimeError('STOP: source is not A260; do not apply A261')
    if 'A261 advanced controls toggle:' in original and 'a261-progressive-dashboard' in original:
        return {'changed':False,'sha256':sha(original)}
    if 'A261 advanced controls toggle:' in original or 'a261-progressive-dashboard' in original:
        raise RuntimeError('STOP: incomplete A261 source, manual review needed')
    # Use exact anchors scoped to the dashboard f-string, never to DB logic.
    css_anchor='    </style>\n    <div class=\'pro-dashboard a2-dashboard'
    if original.count(css_anchor)!=1: raise RuntimeError('STOP: CSS anchor missing or ambiguous')
    content=original.replace(css_anchor,CSS.replace('{','{{').replace('}','}}')+'\n'+css_anchor,1)
    # We leave the original heavy panels at root level for legacy JS / drag handles.
    anchor="      </section>\n\n      <section class='a3-command-hero a6-command-hero'"
    if content.count(anchor)!=1: raise RuntimeError('STOP: UI insertion anchor ambiguous')
    content=content.replace(anchor,'      </section>\n'+BUTTON+"\n      <section class='a3-command-hero a6-command-hero'",1)
    # Important: template is f-string; no JS braces may be interpreted as f-string expressions.
    end='    </div>\n    """\n    return layout(html)'
    if content.count(end)!=1: raise RuntimeError('STOP: dashboard end anchor ambiguous')
    content=content.replace(end,'    </div>\n'+JS.replace('{','{{').replace('}','}}')+'    """\n    return layout(html)',1)
    # Fix misleading claim when actual alerts are present.
    bogus='<strong>Tutto in regola</strong><span class=\'a260-big\' aria-hidden=\'true\'>✓</span>'
    true_label="<strong>{'Tutto in regola' if total_actions == 0 else 'Consulta le schede'}</strong><span class='a260-big' aria-hidden='true'>✓</span>"
    if content.count(bogus)==1: content=content.replace(bogus,true_label,1)
    elif true_label not in content:raise RuntimeError('STOP: state title anchor missing')
    compile(content,str(path),'exec')
    path.write_text(content,encoding='utf-8')
    return {'changed':True,'before_sha256':sha(original),'after_sha256':sha(content)}

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(); p.add_argument('--root',required=True)
    a=p.parse_args(); print(json.dumps(patch(a.root),indent=2))