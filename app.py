from flask import Flask, request, jsonify, send_from_directory
# from flask_cors import CORS; CORS(app)
import os
import base64
from datetime import datetime
import traceback
from openai import OpenAI

import uuid
import json
import requests
import firebase_admin
from firebase_admin import credentials, storage

app = Flask(__name__)

# ------------------- Config -------------------
FIREBASE_URL = "https://lotteryview-default-rtdb.asia-southeast1.firebasedatabase.app/users"
BUCKET_NAME = "lotteryview.firebasestorage.app"  # ต้องตรงกับชื่อ bucket จริงใน Firebase Console
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# โหลด service account จาก Environment Variable
service_account_json = os.environ.get("FIREBASE_SERVICE_KEY")
if not service_account_json:
    raise Exception("❌ Environment variable FIREBASE_SERVICE_KEY not set")

cred = credentials.Certificate(json.loads(service_account_json))
firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ ERROR: OPENAI_API_KEY is not set in environment")

client = OpenAI(api_key=OPENAI_API_KEY)


# ------------------- Routes -------------------
@app.route("/")
def index():
    return "✅ Server is running! (OpenAI API mode)"


# ------------------- ฟังก์ชันเรียก OpenAI -------------------
def ask_openai(filepath, question):
    with open(filepath, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "คุณเป็นผู้ช่วยวิเคราะห์ภาพ"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ]
    )

    return response.choices[0].message.content


@app.route("/upload_image", methods=["POST"])
def upload_image():
    try:
        data = request.json
        image_b64 = data.get("image_base64")
        question = data.get("question", "")

        if not image_b64:
            return jsonify({"error": "No image provided"}), 400

        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(image_b64))

        ai_answer = ask_openai(filepath, question)

        return jsonify({
            "answer": ai_answer,
            "filename": filename
        })

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/upload_image/<filename>")
def get_uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/list_images")
def list_images():
    try:
        files = os.listdir(UPLOAD_FOLDER)
        files.sort(reverse=True)
        urls = [request.host_url + "upload_image/" + f for f in files]
        return jsonify({"images": urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------- บันทึก Profile ใน Firebase -------------------
@app.route("/save_user", methods=["POST"])
def save_user():
    try:
        data = request.json
        shop_name = data.get("shop_name")
        user_name = data.get("user_name")
        phone = data.get("phone")
        user_id = data.get("user_id")  # รับจาก MAUI

        if not shop_name or not user_name or not phone:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        if not user_id:
            user_id = str(uuid.uuid4())

        payload = {
            "shop_name": shop_name,
            "user_name": user_name,
            "phone": phone
        }

        url = f"{FIREBASE_URL}/{user_id}/profile.json"
        res = requests.put(url, data=json.dumps(payload))

        if res.status_code == 200:
            return jsonify({"message": "บันทึก profile สำเร็จ", "id": user_id}), 200
        else:
            return jsonify({"error": res.text}), res.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------- บันทึกภาพลง Firebase Storage + Realtime DB -------------------
@app.route("/save_image", methods=["POST"])
def save_image():
    try:
        data = request.json
        user_id = data.get("user_id")
        image_base64 = data.get("image_base64")
        number6 = data.get("number6")
        quantity = data.get("quantity")

        if not user_id or not image_base64 or not number6 or not quantity:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        image_bytes = base64.b64decode(image_base64)
        filename = f"{str(uuid.uuid4())}.jpg"
        filepath = os.path.join("/tmp", filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        bucket = storage.bucket()
        blob = bucket.blob(f"users/{user_id}/imagelottery/{filename}")
        blob.upload_from_filename(filepath)
        blob.make_public()

        image_url = blob.public_url
        ticket_id = str(uuid.uuid4())

        payload = {
            "image_url": image_url,
            "number6": number6,
            "quantity": quantity
        }

        url = f"{FIREBASE_URL}/{user_id}/imagelottery/{ticket_id}.json"
        res = requests.put(url, data=json.dumps(payload))

        if res.status_code == 200:
            return jsonify({"message": "บันทึกสำเร็จ", "ticket_id": ticket_id}), 200
        else:
            return jsonify({"error": res.text}), res.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------- ค้นหาเลขจาก Firebase -------------------
@app.route("/search_number", methods=["POST"])
def search_number():
    try:
        data = request.json
        number = data.get("number")  # เช่น "12", "123", "123456"

        if not number:
            return jsonify({"error": "ต้องใส่เลขที่ต้องการค้นหา"}), 400

        print(f"🔍 Searching for number: {number}")
        results = []

        # ดึงข้อมูลทั้งหมดจาก Firebase
        res = requests.get(f"{FIREBASE_URL}.json")
        if res.status_code != 200:
            return jsonify({"error": "ไม่สามารถเชื่อมต่อ Firebase ได้"}), 500

        all_users = res.json()
        if not all_users:
            return jsonify({"results": []}), 200

        search_len = len(number)

        # วนเช็คเลขแต่ละ user
        for user_id, user_data in all_users.items():
            imagelottery = user_data.get("imagelottery", {})
            for ticket_id, ticket_data in imagelottery.items():
                number6 = ticket_data.get("number6", "")
                match_type = None

                # ---------- 2 ตัว ----------
                if search_len == 2:
                    if number == number6[-2:]:
                        match_type = "2 ตัวบน"   # หลักสิบ+หน่วยท้าย
                    elif number == number6[:2]:
                        match_type = "2 ตัวล่าง" # สองหลักหน้า

                # ---------- 3 ตัว ----------
                elif search_len == 3:
                    if number == number6[-3:]:
                        match_type = "3 ตัวบน"   # ร้อย+สิบ+หน่วยท้าย
                    elif number == number6[:3]:
                        match_type = "3 ตัวล่าง" # สามหลักหน้า

                # ---------- 6 ตัว ----------
                elif search_len == 6:
                    if number == number6:
                        match_type = "6 ตัวตรง"

                # ถ้า match → เก็บผลลัพธ์
                if match_type:
                    results.append({
                        "user_id": user_id,
                        "ticket_id": ticket_id,
                        "image_url": ticket_data.get("image_url"),
                        "number6": number6,
                        "quantity": ticket_data.get("quantity"),
                        "match_type": match_type
                    })

        return jsonify({"results": results}), 200

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500



# ------------------- Run -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
