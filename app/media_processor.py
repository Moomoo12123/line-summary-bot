import os
import base64
import logging
import anthropic

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def describe_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """แปลงรูปเป็นข้อความ เพื่อเก็บลง DB ให้สรุปได้ทีหลัง"""
    try:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": "อธิบายสิ่งที่เห็นในรูปนี้เป็นภาษาไทย ระบุรายละเอียดที่สำคัญ เช่น ข้อความในรูป สิ่งของ กิจกรรม ใน 2-3 ประโยค"
                    }
                ]
            }]
        )
        return f"[รูปภาพ: {response.content[0].text.strip()}]"
    except Exception as e:
        logger.error(f"Error describing image: {e}")
        return "[รูปภาพ: ไม่สามารถอ่านได้]"


def extract_pdf(pdf_bytes: bytes) -> str:
    """แปลง PDF เป็นข้อความ เพื่อเก็บลง DB ให้สรุปได้ทีหลัง"""
    try:
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": "อ่านและสกัดเนื้อหาสำคัญทั้งหมดในไฟล์นี้เป็นภาษาไทย ระบุข้อมูลสำคัญให้ครบถ้วน"
                    }
                ]
            }]
        )
        return f"[ไฟล์ PDF: {response.content[0].text.strip()}]"
    except Exception as e:
        logger.error(f"Error extracting PDF: {e}")
        return "[ไฟล์ PDF: ไม่สามารถอ่านได้]"
