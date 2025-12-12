from sqlmodel import SQLModel, Field
from datetime import datetime

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str
    password_hash: str
    role: str = "admin"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Machine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    device_name: str
    mac_address: str
    owner: str | None = None
    status: str = "active"
    last_seen: datetime | None = None

class BlockLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    machine_id: int
    action: str
    by_user: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
