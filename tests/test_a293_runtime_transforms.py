"""A293 SHA-pinned transforms test on intentionally synthetic source fragments."""
import hashlib
import unittest
from unittest.mock import patch
from fixes.a293 import patch_family_promemoria as reminder
from fixes.a293 import patch_a291_generic_checkout as method

class TestA293SourceSafety(unittest.TestCase):
    def test_generic_link_removed_only_on_verified_exact_match(self):
        src=b"def family_payment_options():\n"+method.OLD.encode()+b"\n"
        with patch.object(method,"SOURCE_SHA",hashlib.sha256(src).hexdigest()):
            out=method.transform(src)
        self.assertIn(method.MARKER.encode(),out)
        self.assertNotIn(b"if 'sumup' not in choices and general_sumup:",out)
        with self.assertRaises(ValueError):method.transform(src)

    def test_personal_whatsapp_requires_matching_source(self):
        src=("def _a17_phone_for_tesserato(conn, tid: int) -> str:\n    return ''\n"
            "def test():\n"+reminder.EXACT+"\n").encode()
        with patch.object(reminder,"SOURCE_SHA",hashlib.sha256(src).hexdigest()):
            out=reminder.transform(src)
        self.assertIn(reminder.MARKER.encode(),out)
        self.assertIn(b"family_ref = _a293_reminder_family_access(conn, tid, phone)",out)
        self.assertIn(b"if phone and family_ref else",out)
        with self.assertRaises(ValueError):reminder.transform(src)
if __name__=="__main__":
    unittest.main()
