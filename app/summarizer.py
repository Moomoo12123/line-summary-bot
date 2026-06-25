import os
import json
import logging
import anthropic
from datetime import datetime
import pytz

from app.database import (
    get_messages_in_cycle,
    get_message_count_in_cycle,
    get_summary_cycle,
)

logger = logging.getLogger(__name__)
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """คุณเป็น AI ผู้ช่วยสรุปบทสนทนาในกลุ่ม LINE ภาษาไทย

หน้าที่ของคุณ:
1. วิเคราะห์บทสนทนาและตัดสินใจว่าควรสรุปหัวข้อใดบ้างตามเนื้อหาจริง
2. ไม่ต้องใส่หัวข้อที่ไม่มีข้อมูลสนับสนุน
3. ตอบกลับเป็น JSON เสมอตามรูปแบบที่กำหนด

รูปแบบ JSON ที่ต้องตอบกลับ:
{
  "has_content": true/false,
  "topic": "หัวข้อหลักของรอบนี้ (1 บรรทัด)",
  "sections": [
    {
      "type": "key_points" | "action_items" | "decisions" | "announcements" | "conflicts" | "highlights",
      "label": "ชื่อหัวข้อภาษาไทย",
      "emoji": "emoji ที่เหมาะสม",
      "items": ["รายการ 1", "รายการ 2"]
    }
  ],
  "mood": "positive" | "neutral" | "tense",
  "activity_level": "low" | "medium" | "high"
}

section types:
- key_points: ประเด็นสำคัญที่พูดถึง
- action_items: งานหรือสิ่งที่ต้องทำ
- decisions: การตัดสินใจที่เกิดขึ้น
- announcements: ประกาศหรือแจ้งข่าว
- conflicts: ความขัดแย้งที่ยังไม่ได้ข้อสรุป
- highlights: ช่วงเวลาสำคัญหรือน่าจดจำ

ถ้าบทสนทนาสั้นมากหรือไม่มีสาระ ให้ตั้ง has_content เป็น false"""


def format_messages_for_prompt(messages: list[dict]) -> str:
    return "\n".join(f"[{m['time']}] {m['user_id'][:8]}: {m['text']}" for m in messages)


def build_summary_text(analysis: dict, cycle_start: datetime, cycle_end: datetime, msg_count: int) -> str:
    # แสดงช่วงเวลาของรอบที่สรุป
    start_str = cycle_start.strftime("%d/%m %H:%M")
    end_str = cycle_end.strftime("%d/%m %H:%M")

    mood_emoji = {"positive": "😊", "neutral": "😐", "tense": "😬"}.get(analysis.get("mood", "neutral"), "😐")
    activity_emoji = {"low": "🔵", "medium": "🟡", "high": "🔴"}.get(analysis.get("activity_level", "medium"), "🟡")

    lines = [
        f"📋 สรุปบทสนทนา",
        f"🕐 {start_str} → {end_str}",
        f"💬 {msg_count} ข้อความ  {activity_emoji} {mood_emoji}",
        f"📌 {analysis.get('topic', 'การสนทนาทั่วไป')}",
        "─" * 30,
    ]

    for section in analysis.get("sections", []):
        items = section.get("items", [])
        if not items:
            continue
        lines.append(f"\n{section['emoji']} {section['label']}")
        for item in items:
            lines.append(f"  • {item}")

    lines.append("\n─" * 30)
    lines.append("🤖 สรุปโดย AI อัตโนมัติ")
    return "\n".join(lines)


def generate_summary_for_group(group_id: str) -> str | None:
    cycle_start, cycle_end = get_summary_cycle()
    msg_count = get_message_count_in_cycle(group_id, cycle_start, cycle_end)

    if msg_count == 0:
        return None

    messages = get_messages_in_cycle(group_id, cycle_start, cycle_end)
    conversation_text = format_messages_for_prompt(messages)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"กรุณาวิเคราะห์และสรุปบทสนทนาต่อไปนี้:\n\n{conversation_text}"}]
        )

        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        analysis = json.loads(raw)

        if not analysis.get("has_content", True):
            start_str = cycle_start.strftime("%d/%m %H:%M")
            end_str = cycle_end.strftime("%d/%m %H:%M")
            return f"📋 ไม่มีการสนทนาที่มีสาระในรอบนี้\n🕐 {start_str} → {end_str} ({msg_count} ข้อความ) 🤖"

        return build_summary_text(analysis, cycle_start, cycle_end, msg_count)

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {group_id}: {e}")
        return "📋 สรุปรอบนี้ไม่สำเร็จ กรุณาลองใหม่ครั้งหน้า 🤖"
    except Exception as e:
        logger.error(f"Error summarizing {group_id}: {e}")
        return None
