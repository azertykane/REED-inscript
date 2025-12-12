from fastapi import APIRouter, Depends, HTTPException, Form
from sqlmodel import select
from ..models import User
from ..database import get_session
from ..auth import hash_password, create_token, get_current_user

router = APIRouter()

@router.post("/create")
def create_user(username: str = Form(...), password: str = Form(...), session = Depends(get_session)):
    u = User(username=username, password_hash=hash_password(password))
    session.add(u)
    session.commit()
    session.refresh(u)
    return {"ok": True, "user": {"id": u.id, "username": u.username}}

@router.post("/login")
def login(username: str = Form(...), password: str = Form(...), session = Depends(get_session)):
    from ..auth import verify_password
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Username or password incorrect")
    token = create_token(user)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def me(user = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}
