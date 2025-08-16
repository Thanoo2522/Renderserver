from flask import Flask, request, jsonify
import base64
import os
from datetime import datetime
import requests

app = Flask(__name__)

# 📂 โฟลเดอร์เก็บภาพ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 🔑 คีย์และ Token
ACCESS_TOKEN = "thanoo123456"
AI_API_URL = "https://api.openai.com/v1/chat/completions"
AI_API_KEY = os.environ.get("OPENAI_API_KEY")  # อ่านจาก Environment Variables

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
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

        # แปลง Base64 → Bytes
        image_bytes = base64.b64decode(image_base64)

        # บันทึกไฟล์
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        print(f"✅ Image saved to {filepath}")

        # เรียก AI API
        ai_response = call_ai_api(question, filepath)

        return jsonify({
            "status": "success",
            "message": "Image received and analyzed",
            "file": filename,
            "analysis": ai_response
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def call_ai_api(question, image_path):
    """ เรียก OpenAI API ส่งข้อความ + รูปภาพ """
    try:
        with open(image_path, "rb") as img_file:
            image_b64 = base64.b64encode(img_file.read()).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": f"data:image/png;base64,{image_b64}"}
                ]}
            ]
        }

        response = requests.post(AI_API_URL, headers=headers, json=data)
        return response.json()

    except Exception as e:
        return {"error": str(e)}
