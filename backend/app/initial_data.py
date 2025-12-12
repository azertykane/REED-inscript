from .models import User
from .database import engine
from sqlmodel import Session, select
from passlib.hash import bcrypt
from datetime import datetime

def create_admin():
    with Session(engine) as session:
        # Vérifier si l'admin existe déjà
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if not admin:
            password = "admin2K1"
            # tronquer si >72 caractères pour bcrypt
            if len(password) > 72:
                password = password[:72]

            hashed_password = bcrypt.hash(password)

            user = User(
                username="admin",
                password_hash=hashed_password,  # 🔑 utiliser password_hash
                role="admin",
                created_at=datetime.utcnow(),
                is_superuser=True
            )
            session.add(user)
            session.commit()
            print("Admin créé avec succès")
        else:
            print("Admin déjà existant")
