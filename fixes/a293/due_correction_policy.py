"""Pure audit-first correction planning: NO database mutations."""
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
from typing import Optional

@dataclass(frozen=True)
class CorrectionDecision:
    allowed: bool
    reason: str
    prior_due: str = ""
    requested_due: str = ""
    delta: str = ""
    requires_credit_or_refund_workflow: bool = False

def _money(value):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<0 or d!=d.quantize(Decimal("0.01")):
            return None
        return d
    except (TypeError,ValueError,InvalidOperation):
        return None

def evaluate_due_correction(*, old_due, new_due, paid_total, receipt_issued,
                            actor_is_admin, athlete_verified, period_verified,
                            reason, expected_version, current_version,
                            any_pending_payment=False, any_provider_link=False,
                            explicit_accounting_workflow=False):
    """Allow changes to UNPAID obligations only; paid/receipted require separate auditable accounting workflow.

    Caller MUST check tenant and row ownership, concurrency version and authorization,
    then apply the change in a single DB transaction with a nonempty audit entry.
    This module is not a ledger updater.
    """
    old,new,paid=map(_money,(old_due,new_due,paid_total))
    if not actor_is_admin or not athlete_verified or not period_verified:
        return CorrectionDecision(False,"authorization_or_scope")
    if expected_version is None or current_version is None or expected_version!=current_version:
        return CorrectionDecision(False,"stale_version")
    if old is None or new is None or paid is None:
        return CorrectionDecision(False,"invalid_money")
    if not isinstance(reason,str) or len(reason.strip())<12 or len(reason.strip())>1000:
        return CorrectionDecision(False,"reason_required")
    if new==old:
        return CorrectionDecision(False,"no_change")
    if any_pending_payment:
        return CorrectionDecision(False,"pending_payment_must_be_reconciled")
    if any_provider_link:
        return CorrectionDecision(False,"payment_links_must_be_revoked_and_reissued")
    if paid>0 or receipt_issued:
        # Never mutate payment or receipt originals. Even an explicit workflow
        # must independently create linked credit/debit/refund documents.
        return CorrectionDecision(False,"accounting_adjustment_required",
                                  format(old,".2f"),format(new,".2f"),
                                  format(new-old,".2f"),True)
    return CorrectionDecision(True,"unpaid_obligation_update",
                              format(old,".2f"),format(new,".2f"),
                              format(new-old,".2f"),False)
