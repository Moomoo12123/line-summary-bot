import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, func
from sqlalchemy.orm import declarative_base, sessionmaker
import pytz

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./line_bot.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
SUMMARY_HOUR = 18


# ─── Cycle Helper ─────────────────────────────────────────────────────────────

def get_current_cycle() -> tuple[datetime, datetime]:
    now = datetime.now(BANGKOK_TZ)
    if now.hour >= SUMMARY_HOUR:
        cycle_start = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    else:
        yesterday = now - timedelta(days=1)
        cycle_start = yesterday.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    cycle_end = cycle_start + timedelta(hours=24)
    return cycle_start, cycle_end


def get_summary_cycle() -> tuple[datetime, datetime]:
    now = datetime.now(BANGKOK_TZ)
    cycle_end = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    cycle_start = cycle_end - timedelta(hours=24)
    return cycle_start, cycle_end


# ─── Models ───────────────────────────────────────────────────────────────────

class Group(Base):
    __tablename__ = "groups"
    group_id = Column(String(100), primary_key=True)
    group_name = Column(String(200), nullable=True)  # ชื่อกลุ่ม LINE
    joined_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    group_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100))
    text = Column(Text)
    timestamp = Column(DateTime(timezone=True), index=True)


# ─── DB Operations ────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(bind=engine)


def save_group(group_id: str, group_name: str = None):
    db = SessionLocal()
    try:
        existing = db.query(Group).filter(Group.group_id == group_id).first()
        if not existing:
            db.add(Group(group_id=group_id, group_name=group_name))
        elif group_name and existing.group_name != group_name:
            existing.group_name = group_name  # อัปเดตชื่อถ้าเปลี่ยน
        db.commit()
    finally:
        db.close()


def get_group_name(group_id: str) -> str:
    db = SessionLocal()
    try:
        group = db.query(Group).filter(Group.group_id == group_id).first()
        if group and group.group_name:
            return group.group_name
        return group_id[:8] + "..."  # fallback ถ้าไม่มีชื่อ
    finally:
        db.close()


def save_message(group_id: str, user_id: str, text: str, timestamp: datetime):
    db = SessionLocal()
    try:
        if not db.query(Group).filter(Group.group_id == group_id).first():
            db.add(Group(group_id=group_id))
        db.add(Message(
            group_id=group_id,
            user_id=user_id,
            text=text,
            timestamp=timestamp,
        ))
        db.commit()
    finally:
        db.close()


def get_all_groups() -> list[str]:
    db = SessionLocal()
    try:
        return [g.group_id for g in db.query(Group.group_id).filter(Group.active == True).all()]
    finally:
        db.close()


def get_messages_in_cycle(group_id: str, cycle_start: datetime, cycle_end: datetime) -> list[dict]:
    db = SessionLocal()
    try:
        messages = (
            db.query(Message)
            .filter(
                Message.group_id == group_id,
                Message.timestamp >= cycle_start,
                Message.timestamp < cycle_end,
            )
            .order_by(Message.timestamp)
            .all()
        )
        return [
            {"user_id": m.user_id, "text": m.text, "time": m.timestamp.strftime("%H:%M")}
            for m in messages
        ]
    finally:
        db.close()


def get_message_count_in_cycle(group_id: str, cycle_start: datetime, cycle_end: datetime) -> int:
    db = SessionLocal()
    try:
        return db.query(func.count(Message.id)).filter(
            Message.group_id == group_id,
            Message.timestamp >= cycle_start,
            Message.timestamp < cycle_end,
        ).scalar()
    finally:
        db.close()
