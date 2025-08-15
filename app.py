from flask import Flask, request, jsonify
import base64

app = Flask(__name__)

ACCESS_TOKEN = "thanoo123456"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()

    if not data or data.get("token") != ACCESS_TOKEN:
        return jsonify({"error": "Invalid token"}), 403

    base64_image = data.get("image")
    question = data.get("question", "วิเคราะห์ภาพนี้ให้หน่อย")

    image_bytes = base64.b64decode(base64_image)

    ai_response = f"นี่คือคำตอบจำลองสำหรับคำถาม: {question}"

    return jsonify({
        "status": "success",
        "answer": ai_response
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
