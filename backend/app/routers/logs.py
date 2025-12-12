from fastapi import APIRouter, Depends
from sqlmodel import select
from ..models import BlockLog
from ..database import get_session
from ..auth import get_current_user

router = APIRouter()

@router.get("/")
def list_logs(session = Depends(get_session), user = Depends(get_current_user)):
    return session.exec(select(BlockLog).order_by(BlockLog.timestamp.desc())).all()
