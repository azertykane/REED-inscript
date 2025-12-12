from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import select
from passlib.context import CryptContext
from datetime import timedelta, datetime
from jose import jwt, JWTError

from .database import get_session
from .models import User

SECRET_KEY = "AZIZ_SUPER_SECRET_KEY"
ALGO = "HS256"
ACCESS_TOKEN_EXPIRE_MIN = 60 * 24

oauth_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(p, h): return pwd.verify(p, h)
def hash_password(p): return pwd.hash(p)

def create_token(user: User):
    payload = {
        "sub": user.username,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MIN)
    }
    return jwt.encode(payload, SECRET_KEY, ALGO)

def get_current_user(token: str = Depends(oauth_scheme), session = Depends(get_session)):
    from sqlmodel import select
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
        username = data.get("sub")
        user = session.exec(select(User).where(User.username == username)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")
