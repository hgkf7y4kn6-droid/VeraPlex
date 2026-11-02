"""Role -> permission map. Roles are scoped to tenant (site scoping lands with the site model)."""

OPERATOR = {"deviation.create", "deviation.read", "sop.read", "training.ack"}
INVESTIGATOR = OPERATOR | {"deviation.investigate", "capa.create", "capa.read", "ai.adopt", "capa.submit", "sop.author", "change_control.open"}
QA = INVESTIGATOR | {"deviation.triage", "deviation.close", "capa.approve", "capa.close", "audit.read", "audit.verify", "sop.review", "sop.approve", "sop.admin", "change_control.close"}
AREA_OWNER = {"deviation.read", "capa.read", "capa.approve", "capa.action", "sop.read", "sop.review", "training.ack"}
ADMIN = {"audit.read", "audit.verify", "deviation.read", "capa.read", "sop.read", "training.ack"}
# The AI principal reads and drafts. It never holds a regulated-action permission.
AI_AGENT = {"deviation.read", "capa.read", "sop.read", "ai.draft.create"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "operator": OPERATOR,
    "investigator": INVESTIGATOR,
    "qa": QA,
    "area_owner": AREA_OWNER,
    "admin": ADMIN,
    "ai_agent": AI_AGENT,
}

# Backend allowlist: these permissions can never be exercised by a non-human principal,
# whatever the role map or the orchestrator says.
HUMAN_ONLY = {
    "deviation.triage", "deviation.investigate", "deviation.close", "capa.create", "capa.submit",
    "capa.approve", "capa.close", "capa.action", "ai.adopt", "record.sign",
    "sop.author", "sop.review", "sop.approve", "sop.admin", "training.ack", "change_control.open", "change_control.close",
}
