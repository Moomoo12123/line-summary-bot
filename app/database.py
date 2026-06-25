import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, func
from sqlalchemy.orm import declarative_base, sessionmaker
import pytz

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./line_bot.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
SUMMARY_HOUR = 18  # รอบสรุปเริ่มต้นที่ 18:00


# ─── Cycle Helper ─────────────────────────────────────────────────────────────

def get_current_cycle() -> tuple[datetime, datetime]:
    """
    คืนช่วงเวลาของรอบสรุป "ปัจจุบัน" ที่กำลังเก็บข้อมูลอยู่
    
    ตัวอย่าง:
      - ถ้าตอนนี้  08:00 วันอังคาร  → cycle = [18:00 จันทร์ → 17:59 อังคาร]
      - ถ้าตอนนี้  20:00 วันอังคาร  → cycle = [18:00 อังคาร  → 17:59 พุธ]
    """
    now = datetime.now(BANGKOK_TZ)
    if now.hour >= SUMMARY_HOUR:
        # หลัง 18:00 → รอบใหม่เริ่มแล้ว
        cycle_start = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    else:
        # ก่อน 18:00 → ยังอยู่ในรอบของเมื่อวาน
        yesterday = now - timedelta(days=1)
        cycle_start = yesterday.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    
    cycle_end = cycle_start + timedelta(hours=24)
    return cycle_start, cycle_end


def get_summary_cycle() -> tuple[datetime, datetime]:
    """
    คืนช่วงเวลาของรอบที่ "ควรสรุปตอนนี้" (รอบที่เพิ่งปิด)
    เรียกใช้เมื่อ job 18:00 รัน
    
    ตัวอย่าง:
      - Job รันตอน 18:00 วันอังคาร → สรุปข้อความ [18:00 จันทร์ → 17:59 อังคาร]
    """
    now = datetime.now(BANGKOK_TZ)
    # รอบที่เพิ่งจบคือ 18:00 เมื่อวาน → 17:59 วันนี้
    cycle_end = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    cycle_start = cycle_end - timedelta(hours=24)
    return cycle_start, cycle_end


# ─── Models ───────────────────────────────────────────────────────────────────

class Group(Base):
    __tablename__ = "groups"
    group_id = Column(String(100), primary_key=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    group_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100))
    text = Column(Text)
    timestamp = Column(DateTime, index=True)  # เวลาจริงของข้อความ (timezone-aware)


# ─── DB Operations ────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(bind=engine)


def save_group(group_id: str):
    db = SessionLocal()
    try:
        if not db.query(Group).filter(Group.group_id == group_id).first():
            db.add(Group(group_id=group_id))
            db.commit()
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
    """ดึงข้อความในช่วง cycle_start (inclusive) ถึง cycle_end (exclusive)"""
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
