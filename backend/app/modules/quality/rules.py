"""Deterministic quality rules. No AI here by design."""
from app.modules.records.service import StateMachine

# Provisional ICH Q9-style matrix: severity x occurrence x detectability, each 1-5.
# Band cut-offs are defaults pending QA-lead sign-off recorded in the requirements matrix.
MINOR_MAX, MAJOR_MAX = 15, 45


def risk_score(severity: int, occurrence: int, detectability: int) -> tuple[int, str]:
    for v in (severity, occurrence, detectability):
        if not 1 <= v <= 5:
            raise ValueError("ratings must be 1..5")
    score = severity * occurrence * detectability
    return score, ("minor" if score <= MINOR_MAX else "major" if score <= MAJOR_MAX else "critical")


DEVIATION = StateMachine(
    transitions={
        "open": {"triaged"},
        "triaged": {"investigation"},
        "investigation": {"capa_proposed", "closed"},
        "capa_proposed": {"closed"},
    },
    lock_on_enter={"closed"},
)
INVESTIGATION = StateMachine(transitions={"draft": {"complete"}}, lock_on_enter={"complete"})
CAPA = StateMachine(
    transitions={
        "draft": {"pending_approval"},
        "pending_approval": {"approved", "rejected"},
        "approved": {"in_progress"},
        "in_progress": {"effectiveness_check"},
        "effectiveness_check": {"closed"},
    },
    lock_on_enter={"pending_approval", "closed"},
)
REQUIRED_CAPA_APPROVER_ROLES = {"qa", "area_owner"}
CHANGE_CONTROL = StateMachine(
    transitions={"open": {"implemented"}, "implemented": {"closed"}},
    lock_on_enter={"closed"},
)
