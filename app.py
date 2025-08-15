from flask import Flask, request, jsonify
import base64
import os
from datetime import datetime

app = Flask(__name__)

ACCESS_TOKEN = "thanoo123456"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()

    if not data or data.get("token") != ACCESS_TOKEN:
        return jsonify({"error": "Invalid token"}), 403

    base64_image = data.get("image")
    question = data.get("question", "วิเคราะห์ภาพนี้ให้หน่อย")

    # แปลงจาก Base64 → Bytes
    image_bytes = base64.b64decode(base64_image)

    # สร้างโฟลเดอร์ uploads ถ้ายังไม่มี
    os.makedirs("uploads", exist_ok=True)

    # ตั้งชื่อไฟล์ตามเวลา
    filename = f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

    # บันทึกรูปลงเครื่องเซิร์ฟเวอร์
    with open(filename, "wb") as f:
        f.write(image_bytes)

    # ตอบกลับ (ทดสอบ)
    ai_response = f"นี่คือคำตอบจำลองสำหรับคำถาม: {question}"

    return jsonify({
        "status": "success",
        "answer": ai_response,
        "saved_file": filename
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
