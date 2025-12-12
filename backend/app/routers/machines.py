from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from ..models import Machine, BlockLog
from ..database import get_session
from ..auth import get_current_user

router = APIRouter()

@router.get("/")
def list_machines(session = Depends(get_session)):
    return session.exec(select(Machine)).all()

@router.post("/register")
def register_machine(device_name: str, mac: str, session = Depends(get_session)):
    m = Machine(device_name=device_name, mac_address=mac)
    session.add(m)
    session.commit()
    session.refresh(m)
    return {"ok": True, "machine": m}

@router.post("/block/{machine_id}")
def block(machine_id: int, user=Depends(get_current_user), session = Depends(get_session)):
    m = session.get(Machine, machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine non trouvée")
    m.status = "blocked"
    session.add(BlockLog(machine_id=machine_id, action="block", by_user=user.username))
    session.add(m)
    session.commit()
    return {"status": "blocked"}

@router.post("/unblock/{machine_id}")
def unblock(machine_id: int, user=Depends(get_current_user), session = Depends(get_session)):
    m = session.get(Machine, machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine non trouvée")
    m.status = "active"
    session.add(BlockLog(machine_id=machine_id, action="unblock", by_user=user.username))
    session.add(m)
    session.commit()
    return {"status": "active"}

@router.get("/check/{mac}")
def check_status(mac: str, session = Depends(get_session)):
    m = session.exec(select(Machine).where(Machine.mac_address == mac)).first()
    if not m:
        return {"status": "unknown"}
    return {"status": m.status}
