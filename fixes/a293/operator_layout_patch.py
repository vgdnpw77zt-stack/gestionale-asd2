"""A293 operator composer CSS patch, restricted to the existing R155 style block.

Pure transformation; never changes production on its own. It must be validated
on live source and by browser visual QA before any installation.
"""
import hashlib

MARKER="BODYMIND_A293_OPERATOR_COMPOSER_GRID"
CANONICAL="BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL"
R155="BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED"

CSS=r"""
/* BODYMIND_A293_OPERATOR_COMPOSER_GRID
   Scoped to the operator composer. Retain R90 visualViewport and R155 keyboard
   management; fix shrinking columns, overlap and scrollbar ownership. */
.bmo,.bmo-grid,.bmo-chat,.bmo-compose-shell,.bmo-compose {box-sizing:border-box}
.bmo .bmo-chat {min-width:0;min-height:0;overflow:hidden}
.bmo .bmo-messages {min-height:0;overflow-y:auto;overscroll-behavior:contain}
.bmo .bmo-compose-shell {min-width:0;max-width:100%;z-index:10}
html body main.bmo .bmo-compose {
  box-sizing:border-box!important;min-width:0!important;max-width:min(100%,900px)!important;
  display:grid!important;grid-template-columns:44px minmax(0,1fr) 44px 44px!important;
  align-items:center;column-gap:7px;
}
html body main.bmo .bmo-compose>#bmoInput {
  grid-column:2;grid-row:1;
  box-sizing:border-box;min-width:0;max-width:100%;width:100%;
  overflow-y:auto;resize:none;line-height:1.4;
}
html body main.bmo .bmo-compose>.bmo-attach{grid-column:1;grid-row:1}
html body main.bmo .bmo-compose>.bmo-mic{grid-column:3;grid-row:1}
html body main.bmo .bmo-compose>.bmo-send{grid-column:4;grid-row:1}
@media(max-width:800px) {
  html body main.bmo .bmo-compose-shell {
    flex:0 0 auto!important;position:relative!important;inset:auto!important;
    width:100%!important;max-width:100%!important;transform:none!important;
    padding:7px 8px max(8px,env(safe-area-inset-bottom))!important;
  }
  html body main.bmo .bmo-compose {
    width:100%!important;max-width:100%!important;
    grid-template-columns:40px minmax(0,1fr) 40px 40px!important;
    gap:6px!important;height:auto!important;min-height:56px!important;\n    grid-template-rows:minmax(40px,auto)!important;
  }
  html body main.bmo .bmo-compose>#bmoInput {
    width:100%!important;min-width:0!important;max-width:100%!important;
    min-height:40px!important;max-height:112px!important;
    height:auto!important;font-size:16px!important;align-self:center!important;
  }
  html body main.bmo .bmo-compose>.bmo-attach,html body main.bmo .bmo-compose>.bmo-mic,
  html body main.bmo .bmo-compose>.bmo-send {
    height:40px!important;width:40px!important;min-width:40px!important;
    margin:0!important;padding:0!important;align-self:center!important;
  }
  #bmoAttachPicker {display:none!important}
  .bmo-side.bmo-hidden-tools {display:none!important}
}
@media(min-width:801px) {
  .bmo .bmo-compose-shell {width:100%;min-width:0}
  .bmo .bmo-compose {margin:0 auto;min-height:58px}
}
"""

def transform(source: bytes, *, expected_sha256: str) -> bytes:
    """Refuse unknown live revisions, double patches and misplaced style anchors."""
    if not isinstance(source,bytes) or hashlib.sha256(source).hexdigest()!=expected_sha256:
        raise ValueError("Unknown operator live source; refusing CSS patch")
    text=source.decode("utf-8")
    if MARKER in text:
        raise ValueError("A293 already inserted")
    a=text.find(CANONICAL)
    b=text.find(R155,a)
    end=text.find("</style>",a)
    main=text.find('<main class="bmo">',a)
    if not (a>=0 and b>a and end>b and main>end and text.count(CANONICAL)==1):
        raise ValueError("Cannot uniquely isolate R155 operator style; refusing patch")
    if 'id="bmoInput"' not in text or 'id="bmoAttachPicker"' not in text:
        raise ValueError("Required composer structure changed")
    # The operator HTML is embedded in a Python f-string. Literal CSS braces must
    # be doubled or Python will parse selectors/blocks as f-string expressions.
    escaped_css=CSS.replace("{","{{").replace("}","}}")
    candidate=(text[:end]+escaped_css+text[end:]).encode("utf-8")
    compile(candidate,"routes_operator_bodymind.py","exec")
    return candidate
