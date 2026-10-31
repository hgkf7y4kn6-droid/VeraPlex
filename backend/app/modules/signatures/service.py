import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.providers import AuthenticationProvider
from app.modules.audit import service as audit
from app.modules.identity.principal import PermissionDenied, Principal
from app.modules.records import service as records
from app.modules.records.models import RecordVersion
from app.modules.signatures.models import Signature

MEANINGS = {"authored", "reviewed", "approved", "verified"}


def sign(
    session: Session, auth: AuthenticationProvider, signer: Principal, signer_name: str,
    record_id: str, meaning: str, credential: str,
) -> Signature:
    """Re-authenticate, then bind a signature to the hash of the exact record version."""
    signer.forbid_ai("sign")
    if meaning not in MEANINGS:
        raise ValueError(f"meaning must be one of {sorted(MEANINGS)}")
    rec = records.get(session, signer, record_id)
    version = records.get_version(session, rec)
    if meaning == "approved" and version.author_id == signer.user_id:
        raise PermissionDenied("segregation of duties: author cannot approve their own record")
    reauth_id = auth.verify_reauth(signer.user_id, credential)
    sig = Signature(
        id=str(uuid.uuid4()), tenant_id=signer.tenant_id, record_version_id=version.id,
        signer_id=signer.user_id, signer_name=signer_name, meaning=meaning,
        signed_at=datetime.now(UTC), content_hash=version.content_hash, reauth_event_id=reauth_id,
    )
    session.add(sig)
    audit.append(session, signer, action="signature.create", entity_type=rec.type,
                 entity_id=rec.id, new_value={"meaning": meaning, "version": version.version_no,
                                              "content_hash": version.content_hash})
    return sig


def approve(
    session: Session, auth: AuthenticationProvider, signer: Principal, signer_name: str,
    record_id: str, credential: str, reason: str,
) -> None:
    sign(session, auth, signer, signer_name, record_id, "approved", credential)
    records.apply_signed_transition(session, signer, record_id, "approved", reason)


def manifestation(session: Session, signature: Signature) -> str:
    """Name, date/time and meaning rendered on every view and export; verifies the hash binding."""
    version = session.get(RecordVersion, signature.record_version_id)
    valid = version is not None and version.content_hash == signature.content_hash
    flag = "" if valid else " [INVALID: record changed after signing]"
    return f"{signature.signer_name} · {signature.signed_at:%Y-%m-%d %H:%M:%S} UTC · {signature.meaning}{flag}"


def for_version(session: Session, version_id: str) -> list[Signature]:
    return list(session.scalars(select(Signature).where(Signature.record_version_id == version_id)))
