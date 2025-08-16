from flask import Flask, request, jsonify
import base64
import os
from datetime import datetime
import requests  # ใช้สำหรับเรียก AI API ต่อไป

app = Flask(__name__)

# 📂 กำหนดโฟลเดอร์เก็บภาพข้างๆไฟล์ Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ACCESS_TOKEN = "thanoo123456"

# 🔹 URL ของ AI API (เปลี่ยนเป็น API จริงที่คุณใช้)
AI_API_URL = "https://api.openai.com/v1/chat/completions"
AI_API_KEY = "YOUR_OPENAI_API_KEY"  # ใส่ API Key ของคุณ

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        # ✅ อ่าน JSON จาก MAUI
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON received"}), 400

        token = data.get("token")
        if token != ACCESS_TOKEN:
            return jsonify({"error": "Invalid token"}), 403

        image_base64 = data.get("image")
        question = data.get("question", "Analyze this image")
        if not image_base64:
            return jsonify({"error": "No image data"}), 400

        # ✅ แปลง Base64 → Bytes
        image_bytes = base64.b64decode(image_base64)

        # ✅ ตั้งชื่อไฟล์และบันทึก
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        print(f"✅ Image saved to {filepath}")

        # ✅ ส่งไปให้ AI วิเคราะห์
        ai_response = call_ai_api(question, filepath)

        # ✅ ส่งผลกลับไปให้ MAUI
        return jsonify({
            "status": "success",
            "message": "Image received and analyzed",
            "file": filename,
            "analysis": ai_response
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def call_ai_api(question, image_path):
    """
    ฟังก์ชันเรียก AI API (OpenAI Vision API ตัวอย่าง)
    """
    try:
        with open(image_path, "rb") as img_file:
            files = {
                "file": (os.path.basename(image_path), img_file, "image/png")
            }
            headers = {
                "Authorization": f"Bearer {AI_API_KEY}"
            }
            # สมมุติใช้ Vision API ที่รองรับการส่งไฟล์ + คำถาม
            response = requests.post(
                AI_API_URL,
                headers=headers,
                files=files,
                data={"prompt": question}
            )

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"AI API error {response.status_code}"}

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
