import os
import logging
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, JoinEvent
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

from app.database import init_db, save_message, save_group, get_all_groups
from app.summarizer import generate_summary_for_group

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# LINE config
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")


# ─── Webhook ──────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(JoinEvent)
def handle_join(event):
    """Bot ถูกเพิ่มเข้ากลุ่ม — บันทึก group_id"""
    source = event.source
    if source.type == "group":
        save_group(source.group_id)
        logger.info(f"Joined group: {source.group_id}")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """รับข้อความจากกลุ่ม — เก็บลง DB"""
    source = event.source
    if source.type != "group":
        return

    group_id = source.group_id
    user_id = getattr(source, "user_id", "unknown")
    text = event.message.text
    ts = datetime.fromtimestamp(event.timestamp / 1000, tz=BANGKOK_TZ)

    logger.info(f"Saving message from group: {group_id}, user: {user_id}, text: {text[:30]}")
    save_message(group_id=group_id, user_id=user_id, text=text, timestamp=ts)


# ─── Daily Summary Job ────────────────────────────────────────────────────────

def run_daily_summary():
    """รันทุกวัน 18:00 — สรุปแต่ละกลุ่มแล้วส่งกลับ"""
    logger.info("Starting daily summary job...")
    groups = get_all_groups()

    # Fallback: ใช้ TARGET_GROUP_ID ถ้า DB ว่าง
    target = os.environ.get("TARGET_GROUP_ID")
    if not groups and target:
        logger.info(f"No groups in DB, using TARGET_GROUP_ID: {target}")
        save_group(target)
        groups = [target]

    logger.info(f"Found {len(groups)} groups to summarize")

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        for group_id in groups:
            try:
                summary = generate_summary_for_group(group_id)
                if summary:
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=group_id,
                            messages=[TextMessage(text=summary)]
                        )
                    )
                    logger.info(f"Sent summary to {group_id}")
                else:
                    logger.info(f"No messages today for {group_id}, skipping")
            except Exception as e:
                logger.error(f"Error summarizing {group_id}: {e}")


# ─── Scheduler ────────────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=BANGKOK_TZ)
    scheduler.add_job(run_daily_summary, "cron", hour=18, minute=0)
    scheduler.start()
    logger.info("Scheduler started — daily summary at 18:00 Bangkok time")


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return {"status": "ok", "time": datetime.now(BANGKOK_TZ).isoformat()}


@app.route("/debug-db")
def debug_db():
    from app.database import SessionLocal, Message, Group, get_summary_cycle
    db = SessionLocal()
    groups = db.query(Group).all()
    messages = db.query(Message).order_by(Message.timestamp.desc()).limit(10).all()
    cycle_start, cycle_end = get_summary_cycle()
    db.close()
    return {
        "groups": [g.group_id for g in groups],
        "recent_messages": [
            {"group_id": m.group_id, "text": m.text, "time": str(m.timestamp)}
            for m in messages
        ],
        "summary_cycle": {
            "start": str(cycle_start),
            "end": str(cycle_end)
        }
    }


@app.route("/register-group")
def register_group():
    group_id = request.args.get("id")
    if not group_id:
        return {"error": "missing ?id=GROUP_ID"}, 400
    save_group(group_id)
    logger.info(f"Manually registered group: {group_id}")
    return {"status": "registered", "group_id": group_id}


@app.route("/trigger-summary")
def trigger_summary():
    run_daily_summary()
    return {"status": "summary triggered", "time": datetime.now(BANGKOK_TZ).isoformat()}


# ─── Entrypoint ───────────────────────────────────────────────────────────────

# Start scheduler when module loads (works with gunicorn)
init_db()
start_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
