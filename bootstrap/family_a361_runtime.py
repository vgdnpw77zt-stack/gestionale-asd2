"""A361: inspect structural CSS metrics only, never names, media or URLs."""
import json
from flask import Response, request
_MAX_LOGS=40
_report_count=0
_SCRIPT=b'<script id="bodymind-a361-probe" defer src="/_bodymind_a361_probe.js"></script>'
_MARK=b'id="bodymind-a361-probe"'
_ALLOWED=("family","inner","doc","mobile","viewport","hero","content","intro","video","sky",
          "beforeAnimation","beforeContent","skyAnimation","stylePresent","styleLoaded","styles")
def install(app,script_loader):
    @app.get("/_bodymind_a361_probe.js")
    def _bm361_js():
        response=Response(script_loader(),mimetype="application/javascript")
        response.headers["Cache-Control"]="no-store, max-age=0"
        response.headers["X-Content-Type-Options"]="nosniff"
        return response
    @app.post("/_bodymind_a361_probe")
    def _bm361_measure():
        global _report_count
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or len(request.get_data())>3200:
            return ("",204)
        if data.get("family") is not True:
            return ("",204)
        # Trust only an allowlisted, bounded primitive schema. No freeform content or IDs.
        output={}
        for key in _ALLOWED:
            value=data.get(key)
            if key in ("hero","content","intro","video","sky"):
                if not isinstance(value,dict):continue
                output[key]={}
                for prop in ("found","position","display","width","height","top","left","z",
                             "opacity","overflow","bgTransparent"):
                    v=value.get(prop)
                    if isinstance(v,(bool,int,float)) and abs(v)<100000:
                        output[key][prop]=v
                    elif isinstance(v,str) and len(v)<=24 and prop in ("position","display","z","opacity","overflow"):
                        output[key][prop]=v
            elif isinstance(value,bool):output[key]=value
            elif isinstance(value,(int,float)) and abs(value)<100000:output[key]=value
            elif isinstance(value,str) and key in ("beforeAnimation","skyAnimation","beforeContent"):
                output[key]=value[:44]
        if _report_count<_MAX_LOGS:
            _report_count+=1
            print("BODYMIND A361 FAMILY LAYOUT "+json.dumps(output,sort_keys=True),flush=True)
        return ("",204)
    @app.after_request
    def _bm361_html(response):
        if not (request.method=="GET" and request.path.startswith("/app-tesserato/")
                and response.status_code==200 and response.mimetype=="text/html"
                and not response.direct_passthrough):
            return response
        body=response.get_data()
        if _MARK in body:return response
        low=body.lower()
        point=low.rfind(b"</body>")
        if point<0:return response
        response.set_data(body[:point]+_SCRIPT+b"\n"+body[point:])
        response.headers.pop("ETag",None)
        return response
