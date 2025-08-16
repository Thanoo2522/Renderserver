from flask import Flask, request, jsonify, send_from_directory
import os
import base64
from datetime import datetime

app = Flask(__name__)

# สร้างโฟลเดอร์เก็บภาพ
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def index():
    return "Server is running!"

@app.route("/upload", methods=["POST"])
def upload_image():
    data = request.json
    image_b64 = data.get("image_base64")
    question = data.get("question", "")

    if not image_b64:
        return jsonify({"error": "No image provided"}), 400

    try:
        image_bytes = base64.b64decode(image_b64)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        return jsonify({
            "message": "Image saved successfully",
            "filename": filename,
            "question_received": question
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ดูภาพย้อนหลัง
@app.route("/uploads/<filename>")
def get_uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
