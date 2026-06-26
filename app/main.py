import os
import logging
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, MessagingApiBlob, PushMessageRequest, TextMessage
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, ImageMessageContent,
    VideoMessageContent, FileMessageContent, JoinEvent
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

from app.database import init_db, save_message, save_group, get_all_groups
from app.summarizer import generate_summary_for_group
from app.media_processor import describe_image, extract_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
TARGET_GROUP_ID = os.environ.get("TARGET_GROUP_ID")

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
    source = event.source
    if source.type == "group":
        save_group(source.group_id)
        logger.info(f"Joined group: {source.group_id}")


# ─── Text ─────────────────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    source = event.source
    if source.type != "group":
        return
    group_id = source.group_id
    user_id = getattr(source, "user_id", "unknown")
    text = event.message.text
    ts = datetime.fromtimestamp(event.timestamp / 1000, tz=BANGKOK_TZ)
    logger.info(f"Text from {group_id}: {text[:30]}")
    save_message(group_id=group_id, user_id=user_id, text=text, timestamp=ts)


# ─── Image ────────────────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    source = event.source
    if source.type != "group":
        return
    group_id = source.group_id
    user_id = getattr(source, "user_id", "unknown")
    ts = datetime.fromtimestamp(event.timestamp / 1000, tz=BANGKOK_TZ)

    try:
        with ApiClient(configuration) as api_client:
            blob_api = MessagingApiBlob(api_client)
            image_bytes = blob_api.get_message_content(message_id=event.message.id)
        text = describe_image(image_bytes)
        logger.info(f"Image from {group_id}: {text[:50]}")
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        text = "[รูปภาพ]"

    save_message(group_id=group_id, user_id=user_id, text=text, timestamp=ts)


# ─── Video ────────────────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event):
    source = event.source
    if source.type != "group":
        return
    group_id = source.group_id
    user_id = getattr(source, "user_id", "unknown")
    ts = datetime.fromtimestamp(event.timestamp / 1000, tz=BANGKOK_TZ)
    logger.info(f"Video from {group_id}")
    save_message(group_id=group_id, user_id=user_id, text="[วิดีโอ]", timestamp=ts)


# ─── File (PDF) ───────────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=FileMessageContent)
def handle_file(event):
    source = event.source
    if source.type != "group":
        return
    group_id = source.group_id
    user_id = getattr(source, "user_id", "unknown")
    ts = datetime.fromtimestamp(event.timestamp / 1000, tz=BANGKOK_TZ)
    file_name = event.message.file_name or "file"

    try:
        with ApiClient(configuration) as api_client:
            blob_api = MessagingApiBlob(api_client)
            file_bytes = blob_api.get_message_content(message_id=event.message.id)

        if file_name.lower().endswith(".pdf"):
            text = extract_pdf(file_bytes)
        else:
            text = f"[ไฟล์: {file_name}]"

        logger.info(f"File from {group_id}: {file_name}")
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        text = f"[ไฟล์: {file_name}]"

    save_message(group_id=group_id, user_id=user_id, text=text, timestamp=ts)


# ─── Daily Summary Job ────────────────────────────────────────────────────────

def run_daily_summary():
    logger.info("Starting daily summary job...")

    if not TARGET_GROUP_ID:
        logger.error("TARGET_GROUP_ID not set!")
        return

    groups = get_all_groups()
    logger.info(f"Found {len(groups)} groups, sending to: {TARGET_GROUP_ID}")

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        all_summaries = []

        for group_id in groups:
            try:
                summary = generate_summary_for_group(group_id)
                if summary:
                    all_summaries.append(summary)
                    logger.info(f"Generated summary for {group_id}")
                else:
                    logger.info(f"No messages today for {group_id}, skipping")
            except Exception as e:
                logger.error(f"Error summarizing {group_id}: {e}")

        if all_summaries:
            full_summary = "\n\n".join(all_summaries)
            try:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=TARGET_GROUP_ID,
                        messages=[TextMessage(text=full_summary)]
                    )
                )
                logger.info(f"Sent summary to TARGET_GROUP_ID: {TARGET_GROUP_ID}")
            except Exception as e:
                logger.error(f"Error sending to TARGET_GROUP_ID: {e}")
        else:
            logger.info("No summaries to send today")


# ─── Scheduler ────────────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=BANGKOK_TZ)
    scheduler.add_job(run_daily_summary, "cron", hour=18, minute=0)
    scheduler.start()
    logger.info("Scheduler started — daily summary at 18:00 Bangkok time")


# ─── Endpoints ────────────────────────────────────────────────────────────────

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
        "target_group_id": TARGET_GROUP_ID,
        "groups": [g.group_id for g in groups],
        "recent_messages": [
            {"group_id": m.group_id, "text": m.text[:50], "time": str(m.timestamp)}
            for m in messages
        ],
        "summary_cycle": {"start": str(cycle_start), "end": str(cycle_end)}
    }


@app.route("/register-group")
def register_group():
    group_id = request.args.get("id")
    if not group_id:
        return {"error": "missing ?id=GROUP_ID"}, 400
    save_group(group_id)
    return {"status": "registered", "group_id": group_id}


@app.route("/trigger-summary")
def trigger_summary():
    run_daily_summary()
    return {"status": "summary triggered", "time": datetime.now(BANGKOK_TZ).isoformat()}


# ─── Entrypoint ───────────────────────────────────────────────────────────────

init_db()
start_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
