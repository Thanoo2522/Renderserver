from flask import Flask, request, jsonify, send_from_directory
import os
import base64
from datetime import datetime
from openai import OpenAI   # pip install openai

app = Flask(__name__)

# ------------------- Config -------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ACCESS_TOKEN = "thanoo123456"  # ให้ตรงกับที่ MAUI ใช้
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # ตั้งใน Render Dashboard > Environment

client = OpenAI(api_key=OPENAI_API_KEY)

# ------------------- Index -------------------
@app.route("/")
def index():
    return "Server is running!"

# ------------------- Upload -------------------
@app.route("/upload_image", methods=["POST"])
def upload_image():
    data = request.json
    token = data.get("token")
    image_b64 = data.get("image_base64")
    question = data.get("question", "")

    # ตรวจสอบ token
    if token != ACCESS_TOKEN:
        return jsonify({"error": "Invalid token"}), 403

    if not image_b64:
        return jsonify({"error": "No image provided"}), 400

    try:
        # decode และบันทึกรูป
        image_bytes = base64.b64decode(image_b64)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # ------------------- เรียก AI -------------------
        # แปลงเป็น base64 อีกครั้งส่งให้ AI (OpenAI Vision)
        image_b64_for_ai = base64.b64encode(image_bytes).decode("utf-8")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # หรือ gpt-4.1
            messages=[
                {"role": "system", "content": "คุณเป็นผู้ช่วยวิเคราะห์โรคพืชจากภาพ"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64_for_ai}"}}
                    ]
                }
            ]
        )

        ai_answer = response.choices[0].message.content

        # ส่งกลับให้ MAUI ใช้ได้ตรงๆ
        return jsonify({
            "answer": ai_answer,
            "filename": filename
        })
    except Exception as e:
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
        files.sort(reverse=True)  # เรียงจากใหม่ไปเก่า
        urls = [
            request.host_url + "upload_image/" + f
            for f in files
        ]
        return jsonify({"images": urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------- Run -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
