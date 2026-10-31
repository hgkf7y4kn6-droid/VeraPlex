from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.identity.auth import current_principal, get_auth_provider
from app.modules.identity.principal import PermissionDenied, Principal
from app.modules.records import service as records
from app.modules.signatures import service as signatures

app = FastAPI(title="VeraPlex API")


class CreateRecord(BaseModel):
    type: str
    content: dict


class Transition(BaseModel):
    to_state: str
    reason: str


class Approve(BaseModel):
    signer_name: str
    credential: str
    reason: str


@app.get("/health")
def health():
    return {"status": "ok"}


def _guard(fn):
    try:
        out = fn()
    except PermissionDenied as e:
        raise HTTPException(403, str(e)) from None
    except LookupError:
        raise HTTPException(404, "not found") from None
    except records.InvalidTransition as e:
        raise HTTPException(409, str(e)) from None
    return out


@app.post("/records", status_code=201)
def create_record(body: CreateRecord, p: Principal = Depends(current_principal),
                  s: Session = Depends(get_session)):
    rec = records.create(s, p, body.type, body.content)  # tenant comes from the token only
    s.commit()
    return {"id": rec.id, "state": rec.state}


@app.post("/records/{record_id}/transition")
def transition(record_id: str, body: Transition, p: Principal = Depends(current_principal),
               s: Session = Depends(get_session)):
    rec = _guard(lambda: records.transition(s, p, record_id, body.to_state, body.reason))
    s.commit()
    return {"id": rec.id, "state": rec.state}


@app.post("/records/{record_id}/approve")
def approve(record_id: str, body: Approve, p: Principal = Depends(current_principal),
            s: Session = Depends(get_session), auth=Depends(get_auth_provider)):
    _guard(lambda: signatures.approve(s, auth, p, body.signer_name, record_id,
                                      body.credential, body.reason))
    s.commit()
    return {"id": record_id, "state": "approved"}
