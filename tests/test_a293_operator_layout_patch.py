import hashlib
import unittest
from fixes.a293.operator_layout_patch import transform,MARKER

class TestOperatorLayoutRepair(unittest.TestCase):
    def fixture(self):
        return b'''def operator_ui():
    html = """<!doctype html><html><style>
    /* BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL */
    @media(max-width:800px){.bmo-compose{display:grid}}
    /* BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED */
    </style><main class="bmo"><div class="bmo-compose">
    <input id="bmoAttachPicker"><textarea id="bmoInput"></textarea>
    </div></main></html>"""
    return html
'''
    def test_scoped_css_and_refuse_unverified_inputs(self):
        base=self.fixture()
        sha=hashlib.sha256(base).hexdigest()
        out=transform(base,expected_sha256=sha)
        self.assertEqual(out.count(MARKER.encode()),1)
        self.assertIn(b"grid-template-columns:40px minmax(0,1fr) 40px 40px",out)
        self.assertLess(out.find(MARKER.encode()),out.find(b"</style>"))
        self.assertLess(out.find(b"</style>"),out.find(b'<main class="bmo">'))
        with self.assertRaises(ValueError):
            transform(out,expected_sha256=sha)
        with self.assertRaises(ValueError):
            transform(base,expected_sha256="0"*64)
    def test_no_blind_patch_wrong_component(self):
        base=self.fixture().replace(b'BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED',b'UNVERIFIED_R155')
        with self.assertRaises(ValueError):
            transform(base,expected_sha256=hashlib.sha256(base).hexdigest())
if __name__=="__main__":
    unittest.main()
