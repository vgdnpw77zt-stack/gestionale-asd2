import unittest
from fixes.a293.due_correction_policy import evaluate_due_correction

class DueCorrectionPolicyTests(unittest.TestCase):
    def decision(self,**kw):
        p=dict(old_due="50.00",new_due="40.00",paid_total="0.00",
               receipt_issued=False,actor_is_admin=True,athlete_verified=True,
               period_verified=True,reason="Correzione quota deliberata",
               expected_version=7,current_version=7)
        p.update(kw)
        return evaluate_due_correction(**p)
    def test_unpaid_change_is_eligible_but_does_not_write(self):
        r=self.decision()
        self.assertTrue(r.allowed)
        self.assertEqual(r.delta,"-10.00")
    def test_history_never_overwritten(self):
        for opts in ({"paid_total":"10.00"},{"receipt_issued":True}):
            with self.subTest(opts=opts):
                r=self.decision(**opts)
                self.assertFalse(r.allowed)
                self.assertTrue(r.requires_credit_or_refund_workflow)
    def test_pending_and_links_require_reconciliation(self):
        for opts in ({"any_pending_payment":True},{"any_provider_link":True}):
            self.assertFalse(self.decision(**opts).allowed)
    def test_scope_audit_concurrency_and_amount_guards(self):
        for opts in ({"actor_is_admin":False},{"athlete_verified":False},
                     {"period_verified":False},{"reason":"fix"},
                     {"expected_version":6},{"new_due":"-2"},
                     {"new_due":"NaN"},{"new_due":"40.004"},
                     {"new_due":"50.00"}):
            with self.subTest(opts=opts):self.assertFalse(self.decision(**opts).allowed)

if __name__=="__main__":
    unittest.main()
