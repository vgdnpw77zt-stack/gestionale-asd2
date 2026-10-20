import unittest
from fixes.a293.family_reminder_builder import build_family_reminder

class TestPrivateFamilyReminder(unittest.TestCase):
    def args(self,**changes):
        data=dict(tesserato_id=7,resolved_tesserato_id=7,
            verified_recipient="+390000000000",verified_channel="sms",
            family_url="https://app.bodymindaerialstudio.life/app-tesserato/abcDEF0123456789opaque",
            existing_family_code="123456",consent_or_lawful_basis=True,
            recipient_matches_athlete=True,pending_due_verified=True,
            already_paid=False,period_label="ottobre 2026",amount_eur="45.00")
        data.update(changes)
        return build_family_reminder(**data)
    def test_private_access_details_only_in_verified_draft(self):
        result=self.args()
        self.assertEqual(result.tesserato_id,7)
        self.assertIn("123456",result.body)
        self.assertIn("/app-tesserato/",result.body)
    def test_never_send_mismatched_or_invalid_access(self):
        for changes in ({"resolved_tesserato_id":8},{"recipient_matches_athlete":False},
                        {"consent_or_lawful_basis":False},{"already_paid":True},
                        {"pending_due_verified":False},{"existing_family_code":"?"},
                        {"family_url":"https://evil.test/app-tesserato/abcDEF0123456789opaque"},
                        {"family_url":"http://app.bodymindaerialstudio.life/app-tesserato/abcDEF0123456789opaque"},
                        {"amount_eur":"-4"},{"amount_eur":"NaN"}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.args(**changes))
if __name__=="__main__":
    unittest.main()
