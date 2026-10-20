"""A293: pure source transformation; refuses unknown/changed operator styles.
Requires visual regression QA before any production release.
"""
import ast

MARKER = "BODYMIND_A293_OPERATOR_COMPOSER_LAYOUT"
ANCHOR = "BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL"
R155 = "BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED"

# Double braces because the existing operator HTML template is an f-string.
STYLE = r"""
    /* BODYMIND_A293_OPERATOR_COMPOSER_LAYOUT */
    .bmo,.bmo *{{box-sizing:border-box;}}
    .bmo-chat{{min-width:0!important;min-height:0!important;}}
    .bmo-messages{{min-height:0!important;overflow-y:auto!important;}}
    .bmo-compose-shell{{width:100%!important;max-width:100%!important;min-width:0!important;}}
    .bmo-compose{{box-sizing:border-box!important;min-width:0!important;}}
    .bmo-compose>#bmoInput{{box-sizing:border-box!important;min-width:0!important;max-width:100%!important;}}
    @media(min-width:801px) and (max-width:1280px){{
      .bmo-chat{{min-width:0!important;}}
      .bmo-compose-shell{{padding-inline:12px!important;}}
      .bmo-compose{{max-width:100%!important;}}
    }}
    @media(max-width:800px){{
      .bmo{{min-width:0!important;width:100%!important;max-width:100vw!important;}}
      .bmo-grid{{min-width:0!important;}}
      .bmo-chat{{flex:1 1 auto!important;min-height:0!important;}}
      .bmo-compose-shell{{position:relative!important;inset:auto!important;transform:none!important;
         flex:0 0 auto!important;padding:7px max(6px,env(safe-area-inset-right))
         max(8px,env(safe-area-inset-bottom)) max(6px,env(safe-area-inset-left))!important;}}
      .bmo-compose{{display:grid!important;grid-template-columns:38px minmax(0,1fr) 38px 38px!important;
         grid-template-rows:minmax(42px,auto)!important;gap:5px!important;align-items:center!important;
         width:100%!important;max-width:100%!important;min-height:58px!important;height:auto!important;
         padding:7px!important;overflow:visible!important;}}
      .bmo-compose>.bmo-attach{{grid-column:1!important;grid-row:1!important;}}
      .bmo-compose>#bmoInput{{grid-column:2!important;grid-row:1!important;height:42px!important;
         max-height:120px!important;min-height:42px!important;padding:10px 8px!important;
         font-size:16px!important;line-height:21px!important;resize:none!important;overflow-y:auto!important;}}
      .bmo-compose>.bmo-mic{{grid-column:3!important;grid-row:1!important;}}
      .bmo-compose>.bmo-send{{grid-column:4!important;grid-row:1!important;}}
      .bmo-compose>.bmo-attach,.bmo-compose>.bmo-mic,.bmo-compose>.bmo-send{{
          display:grid!important;place-items:center!important;min-width:38px!important;
          max-width:38px!important;width:38px!important;height:38px!important;
          min-height:38px!important;max-height:38px!important;margin:0!important;padding:0!important;}}
      #bmoAttachPicker,.bmo-side.bmo-hidden-tools{{display:none!important;}}
    }}
"""

def transform(source: bytes) -> bytes:
    text = source.decode("utf-8")
    if MARKER in text:
        raise ValueError("A293 operator patch already installed")
    if text.count(ANCHOR) != 1 or text.count(R155) != 1 or text.count('<main class="bmo">') != 1:
        raise ValueError("Unrecognized operator source: patch refused")
    anchor = text.index(ANCHOR)
    r155 = text.index(R155)
    end = text.find("</style>", anchor)
    main = text.index('<main class="bmo">')
    if not (anchor < r155 < end < main):
        raise ValueError("Operator CSS boundary mismatch")
    output = text[:end] + STYLE + text[end:]
    ast.parse(output)
    return output.encode("utf-8")
