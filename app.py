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
BUCKET_NAME = "lotteryview.firebasestorage.app"  # ✅ ต้องตรงกับ bucket จริง
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


# ------------------- Upload Image -------------------
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


# ------------------- Save User Profile -------------------
@app.route("/save_user", methods=["POST"])
def save_user():
    try:
        data = request.json
        shop_name = data.get("shop_name")
        user_name = data.get("user_name")
        phone = data.get("phone")
        user_id = data.get("user_id")

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


# ------------------- Save Image + Ticket -------------------
@app.route("/save_image", methods=["POST"])
def save_image():
    try:
        data = request.json
        user_id = data.get("user_id")
        image_base64 = data.get("image_base64")
        number6 = str(data.get("number6")).strip()
        quantity = data.get("quantity")

        if not user_id or not image_base64 or not number6 or not quantity:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        # 1️⃣ บันทึกไฟล์ภาพลง Firebase Storage
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

        # 2️⃣ บันทึกข้อมูล Ticket ลง Realtime DB
        payload = {
            "image_url": image_url,
            "number6": number6,
            "quantity": quantity
        }
        url = f"{FIREBASE_URL}/{user_id}/imagelottery/{ticket_id}.json"
        res = requests.put(url, data=json.dumps(payload))
        if res.status_code != 200:
            return jsonify({"error": res.text}), res.status_code

        # 3️⃣ ฟังก์ชันอัปเดต Search Index
        def update_search_index(index_type, num):
            if not num:
                return
            idx_url = f"{FIREBASE_URL.replace('/users', '')}/search_index/{index_type}/{num}/{user_id}/{ticket_id}.json"
            res_idx = requests.put(idx_url, data=json.dumps(True))
            print(f"[INDEX] {idx_url} -> {res_idx.status_code}")

        # 4️⃣ เพิ่มเลขเข้าดัชนีค้นหา
        if len(number6) == 6:
            update_search_index("6_exact", number6)       # เลข 6 ตัวตรง
            update_search_index("3_top", number6[-3:])    # 3 ตัวบน
            update_search_index("3_bottom", number6[:3])  # 3 ตัวล่าง
            update_search_index("2_top", number6[-2:])    # 2 ตัวบน
            update_search_index("2_bottom", number6[:2])  # 2 ตัวล่าง

        return jsonify({
            "message": "บันทึกสำเร็จ",
            "ticket_id": ticket_id,
            "image_url": image_url
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------- Search Ticket -------------------
@app.route("/search_number", methods=["POST"])
def search_number():
    try:
        data = request.json
        number = str(data.get("number")).strip()

        if not number:
            return jsonify({"error": "ต้องใส่เลขที่ต้องการค้นหา"}), 400

        print(f"🔍 Searching for number: {number}")
        results = []
        search_len = len(number)

        if search_len == 2:
            index_types = ["2_top", "2_bottom"]
        elif search_len == 3:
            index_types = ["3_top", "3_bottom"]
        elif search_len == 6:
            index_types = ["6_exact"]
        else:
            return jsonify({"error": "เลขต้องเป็น 2, 3 หรือ 6 หลัก"}), 400

        matched_paths = []
        for idx in index_types:
            idx_url = f"{FIREBASE_URL.replace('/users', '')}/search_index/{idx}/{number}.json"
            res = requests.get(idx_url)
            if res.status_code == 200 and res.json():
                index_data = res.json()  # {user_id: {ticket_id: true}}
                for user_id, tickets in index_data.items():
                    for ticket_id in tickets.keys():
                        matched_paths.append((user_id, ticket_id, idx))

        # 🔄 ดึงข้อมูล Ticket ที่ match
        for user_id, ticket_id, idx in matched_paths:
            ticket_url = f"{FIREBASE_URL}/{user_id}/imagelottery/{ticket_id}.json"
            ticket_res = requests.get(ticket_url)
            if ticket_res.status_code != 200 or not ticket_res.json():
                continue

            ticket_data = ticket_res.json()
            number6 = ticket_data.get("number6", "")
            match_type = None

            if search_len == 2:
                if number == number6[-2:]:
                    match_type = "2 ตัวบน"
                elif number == number6[:2]:
                    match_type = "2 ตัวล่าง"
            elif search_len == 3:
                if number == number6[-3:]:
                    match_type = "3 ตัวบน"
                elif number == number6[:3]:
                    match_type = "3 ตัวล่าง"
            elif search_len == 6:
                if number == number6:
                    match_type = "6 ตัวตรง"

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
