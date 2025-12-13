from fastapi import APIRouter, Depends
from sqlmodel import select
from ..database import get_session
from ..models import BlockLog
from sqlmodel import Session

router = APIRouter()

@router.get("/", summary="List all block/unblock logs")
def list_logs(session: Session = Depends(get_session)):
    logs = session.exec(
        select(BlockLog).order_by(BlockLog.timestamp.desc())
    ).all()
    return logs
