"""A377: Owner-only Bilanci footer on /mobile; presentation-only, no DB access.

The previous A377 collapsible-card experiment is intentionally disabled. This
change does not depend on card titles, DOM selectors or JavaScript execution.
"""
import re
from flask import request

_FOOTER_ID = 'bm-owner-bilanci-footer'
_FOOTER = '''
<section id="bm-owner-bilanci-footer" aria-label="Accesso Bilanci" style="box-sizing:border-box;max-width:100%;margin:24px 12px calc(100px + env(safe-area-inset-bottom, 0px));padding:0;clear:both">
  <a id="bm-owner-bilanci-link" href="/contabilita?bm_owner_bilanci=1" style="box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:70px;padding:16px 18px;border:1px solid #68869b;border-radius:15px;background:#19364b;color:#f8f7f4;text-decoration:none;font-weight:700;box-shadow:0 5px 20px rgba(0,0,0,.12)">
    <span style="display:block;min-width:0">Bilanci<span style="display:block;font-size:.85em;font-weight:400;opacity:.85;margin-top:5px">Contabilità e movimenti</span></span>
    <span aria-hidden="true" style="font-size:1.6em;line-height:1">›</span>
  </a>
</section>
'''
_CLOSING_MAIN = re.compile(r'</main\s*>', re.IGNORECASE)
_CLOSING_BODY = re.compile(r'</body\s*>', re.IGNORECASE)


def add_owner_bilanci_footer(html):
    """Insert as the final Home content, never into the five-item mobile nav."""
    if _FOOTER_ID in html:
        return html  # Idempotent under other response hooks.
    main_closings = list(_CLOSING_MAIN.finditer(html))
    body_closings = list(_CLOSING_BODY.finditer(html))
    if not body_closings:
        return html  # Unknown page structure: fail closed.
    # The closing main in a valid page ends the scrollable content, before nav.
    # Some historical /mobile variants have no <main>: use body footer then.
    anchor = main_closings[-1] if main_closings else body_closings[-1]
    return html[:anchor.start()] + _FOOTER + html[anchor.start():]


def install(app):
    from asd_app.core import auth, has_role

    @app.after_request
    def owner_bilanci_footer(response):
        if (request.method != 'GET'
                or request.path.rstrip('/') != '/mobile'
                or response.status_code != 200
                or response.mimetype != 'text/html'
                or response.direct_passthrough
                or not auth()
                or not has_role('admin')):
            return response
        original = response.get_data(as_text=True)
        updated = add_owner_bilanci_footer(original)
        if updated != original:
            response.set_data(updated)
            response.headers.pop('ETag', None)
            response.headers['Cache-Control'] = 'private, no-store, max-age=0'
            response.headers['Vary'] = 'Cookie'
            response.headers['X-BodyMind-Owner-Bilanci'] = 'A377-footer'
        return response
