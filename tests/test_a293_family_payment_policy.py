import unittest
from fixes.a293.family_payment_policy import family_payment_offer, reminder_access_reference

class PaymentPolicyTests(unittest.TestCase):
    def offer(self, **overrides):
        data=dict(provider="sumup", enabled=True, checkout_url="https://pay.sumup.com/b2c/test",
                  amount_due="45.00", configured_amount="45.00",
                  athlete_matches=True, season_matches=True, paid=False, canceled=False)
        data.update(overrides)
        return family_payment_offer(**data)

    def test_verified_link_is_only_offer_not_payment_record(self):
        result=self.offer()
        self.assertTrue(result.eligible)
        self.assertEqual(result.amount_eur,"45.00")

    def test_suppress_settled_canceled_zero_and_bad_scopes(self):
        for options in ({"paid":True},{"canceled":True},{"amount_due":"0"},
                        {"athlete_matches":False},{"season_matches":False},
                        {"configured_amount":"50.00"},{"enabled":False},
                        {"checkout_url":"http://pay.sumup.com/b2c/test"},
                        {"checkout_url":"https://localhost/pay"},
                        {"checkout_url":"https://user:password@pay.sumup.com/pay"},
                        {"amount_due":"NaN"}):
            with self.subTest(options=options):
                self.assertFalse(self.offer(**options).eligible)

    def test_reminder_requires_verified_token_recipient_and_consent(self):
        valid=dict(access_code="abcDEFghiJKLmnopQRST_123",access_url="https://app.bodymindaerialstudio.life/app-tesserato/abcDEFghiJKLmnopQRST_123",
                   consent_verified=True,recipient_verified=True,audience_matches=True)
        self.assertIsNotNone(reminder_access_reference(**valid))
        for overrides in ({"consent_verified":False},{"recipient_verified":False},
                          {"audience_matches":False},{"access_code":"123"},
                          {"access_url":"http://app.bodymindaerialstudio.life/x"}):
            with self.subTest(options=overrides):
                self.assertIsNone(reminder_access_reference(**(valid|overrides)))

if __name__=="__main__":
    unittest.main()
