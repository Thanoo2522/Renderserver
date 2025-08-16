from flask import Flask, request, jsonify
import os
import base64
from datetime import datetime

app = Flask(__name__)

# โฟลเดอร์เก็บภาพ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Access token
ACCESS_TOKEN = "thanoo123456"

@app.route("/upload", methods=["POST"])
def upload():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON received"}), 400

        token = data.get("token")
        if token != ACCESS_TOKEN:
            return jsonify({"error": "Invalid token"}), 403

        image_base64 = data.get("image")
        if not image_base64:
            return jsonify({"error": "No image data"}), 400

        # แปลง Base64 → ไฟล์ PNG
        image_bytes = base64.b64decode(image_base64)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        return jsonify({
            "status": "success",
            "message": "Image received and saved",
            "file": filename
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # ใช้ port จาก Render
    app.run(host="0.0.0.0", port=port)
