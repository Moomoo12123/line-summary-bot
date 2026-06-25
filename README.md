# 🤖 LINE Group Summary Bot

Bot สรุปบทสนทนากลุ่ม LINE อัตโนมัติด้วย Claude AI — ทุกวันเวลา 18:00 น.

---

## โครงสร้างโปรเจกต์

```
line-summary-bot/
├── app/
│   ├── main.py        # Flask app + Webhook + Scheduler
│   ├── database.py    # SQLite — เก็บข้อความและกลุ่ม
│   └── summarizer.py  # Claude AI วิเคราะห์และสรุป
├── requirements.txt
├── Procfile
├── railway.toml
└── README.md
```

---

## ขั้นตอนที่ 1 — สร้าง LINE Bot

1. ไปที่ https://developers.line.biz → **Log in**
2. สร้าง **Provider** ใหม่
3. สร้าง **Messaging API** channel
4. ในหน้า Basic settings → คัดลอก **Channel Secret**
5. ในหน้า Messaging API → คัดลอก **Channel Access Token** (Issue หากยังไม่มี)
6. เปิด **"Allow bot to join group chats"** = ON
7. ปิด **"Auto-reply messages"** = OFF

---

## ขั้นตอนที่ 2 — Deploy บน Railway

### 2.1 สมัคร Railway
- ไปที่ https://railway.app → Sign up ด้วย GitHub

### 2.2 สร้าง Project
```
New Project → Deploy from GitHub repo → เลือก repo นี้
```

### 2.3 ตั้งค่า Environment Variables
ใน Railway Dashboard → Variables → เพิ่ม:

```
LINE_CHANNEL_SECRET      = <จาก LINE Developers>
LINE_CHANNEL_ACCESS_TOKEN = <จาก LINE Developers>
ANTHROPIC_API_KEY        = <จาก console.anthropic.com>
```

### 2.4 รับ URL
หลัง deploy เสร็จ Railway จะให้ URL เช่น:
```
https://line-summary-bot-production.up.railway.app
```

---

## ขั้นตอนที่ 3 — ตั้ง Webhook ใน LINE

1. กลับไปที่ LINE Developers → Messaging API
2. Webhook URL = `https://YOUR_RAILWAY_URL/webhook`
3. กด **Verify** → ต้องขึ้น Success
4. เปิด **Use webhook** = ON

---

## ขั้นตอนที่ 4 — เพิ่ม Bot เข้ากลุ่ม

1. ใน LINE Developers → Messaging API → คัดลอก **Bot basic ID** (เช่น @abc12345)
2. เปิดกลุ่มที่ต้องการ → เพิ่มเพื่อน → ค้นหา Bot ID
3. เพิ่ม Bot เข้ากลุ่ม
4. Bot จะส่งข้อความต้อนรับอัตโนมัติ

**ทำซ้ำสำหรับทุกกลุ่มที่ต้องการ (รองรับได้ไม่จำกัดกลุ่ม)**

---

## ตัวอย่างสรุปที่จะได้รับ

```
📋 สรุปบทสนทนาวันที่ 24/06/2025
💬 ข้อความทั้งหมด 87 ข้อความ  🔴 😊
📌 ประชุมวางแผน Q3 และนัดหมายทีม
──────────────────────────────

📌 ประเด็นสำคัญ
  • ตั้งเป้ายอดขาย Q3 ที่ 2.5 ล้านบาท
  • ทีมการตลาดขอเพิ่มงบโฆษณา 20%

✅ งานที่ต้องทำ
  • @สมชาย ส่งรายงาน Q2 ภายในวันศุกร์
  • @มานี เตรียม proposal งบประมาณ
  • ทุกคนกรอก feedback form ภายใน 18:00

🎯 การตัดสินใจ
  • อนุมัติงบโฆษณาเพิ่ม 15%
  • นัดประชุมใหญ่วันจันทร์ 9:00 น.

📢 ประกาศ
  • ปิดทำการวันที่ 5 กรกฎาคม

──────────────────────────────
🤖 สรุปโดย AI อัตโนมัติ
```

---

## ราคาโดยประมาณต่อเดือน (40 กลุ่ม)

| บริการ | ราคา |
|--------|------|
| Railway (Hobby plan) | ~$5/เดือน |
| Anthropic API (Claude Sonnet) | ~$2-5/เดือน |
| LINE Messaging API | ฟรี (500 push/เดือน), $35 หากเกิน |
| **รวม** | **~$7-10/เดือน** |

> **หมายเหตุ:** LINE Free plan จำกัด 500 push messages/เดือน
> 40 กลุ่ม × 30 วัน = 1,200 ข้อความ → ควรอัปเกรดเป็น Light plan ($35/เดือน)
> หรือส่งสรุปทุก 2-3 วันแทน เพื่ออยู่ในโควต้าฟรี

---

## คำสั่งเพิ่มเติม (พิมพ์ในกลุ่ม)

Bot ตอบสนองต่อคำสั่ง:
- `/สรุปวันนี้` — สรุปทันที (ยังไม่ implement, สามารถเพิ่มได้)
