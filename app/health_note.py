"""
เพิ่ม health check route เข้าไปใน main.py
"""

HEALTH_ROUTE = """
@app.route("/health")
def health():
    return {"status": "ok", "time": datetime.now(BANGKOK_TZ).isoformat()}
"""
