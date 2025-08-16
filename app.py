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

# ------------------- Upload -------------------
@app.route("/upload_image", methods=["POST"])
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)