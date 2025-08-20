from flask import Flask, request, jsonify, send_from_directory
import os
import base64
from datetime import datetime
import requests

app = Flask(__name__)

# ------------------- Config -------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ACCESS_TOKEN = "thanoo123456"
DEEPINFRA_API_KEY = os.environ.get("DEEPINFRA_API_KEY")

if not DEEPINFRA_API_KEY:
    raise ValueError("❌ ERROR: DEEPINFRA_API_KEY is not set in environment")

# ------------------- Index -------------------
@app.route("/")
def index():
    return "Server is running! (DeepInfra API mode)"

# ------------------- Upload Image + Question -------------------
@app.route("/upload_image", methods=["POST"])
def upload_image():
    try:
        data = request.json
        print("📥 JSON Received:", data)

        token = data.get("token")
        image_b64 = data.get("image_base64")
        question = data.get("question", "")

        if token != ACCESS_TOKEN:
            return jsonify({"error": "Invalid token"}), 403

        if not image_b64:
            return jsonify({"error": "No image provided"}), 400

        # แปลง Base64 เป็นไฟล์ JPG
        image_bytes = base64.b64decode(image_b64)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # ------------------- เรียก DeepInfra -------------------
        url = "https://api.deepinfra.com/v1/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "messages": [
                {"role": "system", "content": "A:คุณคือผู้ช่วย AI ที่ตอบคำถามเกี่ยวกับภาพ"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"คำถาม: {question}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                    ]
                }
            ]
        }

        response = requests.post(url, headers=headers, json=payload)
        result = response.json()
        print("📤 DeepInfra Response:", result)

        # ดึงคำตอบ AI
        ai_answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not ai_answer:
            ai_answer = "❌ AI ไม่สามารถตอบได้"

        return jsonify({
            "answer": ai_answer,
            "filename": filename
        })

    except Exception as e:
        import traceback
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ------------------- Get Image -------------------
@app.route("/upload_image/<filename>")
def get_uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ------------------- List Images -------------------
@app.route("/list_images")
def list_images():
    try:
        files = os.listdir(UPLOAD_FOLDER)
        files.sort(reverse=True)
        urls = [request.host_url + "upload_image/" + f for f in files]
        return jsonify({"images": urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------- Run -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
