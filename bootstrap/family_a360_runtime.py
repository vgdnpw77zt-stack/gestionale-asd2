"""A360: authenticated family HTML stylesheet delivery, no database access.

Last-in-document stylesheet is served under a fixed same-origin public CSS path.
Never log, store, or inspect family tokens or personal response contents.
"""
from flask import Response, request

_ASSET='/_bodymind_family_a360.css'
_LINK=b'<link id="bodymind-a360-style" rel="stylesheet" href="/_bodymind_family_a360.css?v=20261030-a360">'
_MARKER=b'id="bodymind-a360-style"'
def install(app, css_loader):
    # Register at import time, before any request is handled.
    @app.route(_ASSET,methods=['GET'])
    def _bodymind_a360_css():
        css=css_loader()
        resp=Response(css,mimetype='text/css')
        resp.headers['Cache-Control']='no-store, max-age=0'
        resp.headers['X-Content-Type-Options']='nosniff'
        return resp

    @app.after_request
    def _bodymind_a360_html(response):
        # Exclude JSON, videos, documents, and every other private response.
        path=request.path
        if not (request.method=='GET' and path.startswith('/app-tesserato/')
                and response.status_code==200
                and response.mimetype=='text/html' and not response.direct_passthrough):
            return response
        payload=response.get_data()
        # Only a single lightweight link, never modify user content or URLs.
        if _MARKER not in payload:
            low=payload.lower()
            point=low.rfind(b'</body>')
            if point<0:point=low.rfind(b'</head>')
            if point>=0:
                response.set_data(payload[:point]+_LINK+b'\n'+payload[point:])
                response.headers.pop('ETag',None)
        response.headers['Cache-Control']='no-store, max-age=0'
        response.headers['X-BodyMind-Family-UI']='A360'
        return response
