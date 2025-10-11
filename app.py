from flask import Flask, request, jsonify, send_from_directory
import os
import base64
from datetime import datetime
import traceback
import uuid
import json
import time
import requests
import firebase_admin
from firebase_admin import credentials, storage, firestore
 

app = Flask(__name__)

# ------------------- Config -------------------
FIREBASE_URL = "https://lotteryview-default-rtdb.asia-southeast1.firebasedatabase.app/users"
BUCKET_NAME = "lotteryview.firebasestorage.app"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

service_account_json = os.environ.get("FIREBASE_SERVICE_KEY")
cred = credentials.Certificate(json.loads(service_account_json))
firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})

db = firestore.client()
bucket = storage.bucket()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("❌ ERROR: DEEPSEEK_API_KEY is not set in environment")

# ------------------- DeepSeek Function -------------------
def ask_deepseek(filepath, question):
    with open(filepath, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",  # DeepSeek-V3
        "messages": [
            {
                "role": "system",
                "content": "คุณเป็นผู้ช่วยวิเคราะห์ภาพที่เชี่ยวชาญ"
            },
            {
                "role": "user", 
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{image_b64}"
                    },
                    {
                        "type": "text",
                        "text": question
                    }
                ]
            }
        ],
        "max_tokens": 2048
    }
    
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
        
    except requests.exceptions.RequestException as e:
        print(f"❌ DeepSeek API Error: {e}")
        return f"ขออภัย เกิดข้อผิดพลาดในการวิเคราะห์ภาพ: {str(e)}"

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

        # ✅ ใช้ DeepSeek แทน OpenAI
        ai_answer = ask_deepseek(filepath, question)

        return jsonify({
            "answer": ai_answer,
            "filename": filename
        })

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return "✅ Server is running! (DeepSeek-V3 API mode)"

# ------------------- Routes อื่นๆ ที่เหลือ -------------------
# ... routes อื่นๆ ของคุณ ...

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
# ---------------- Route: ดึงข้อมูลเฉพาะฟิลด์ ----------------
@app.route("/get_count", methods=["POST"])
def get_count():
    try:
        data = request.json
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"error": "ต้องระบุ user_id"}), 400

        user_ref = db.collection("count_process").document(user_id)
        doc = user_ref.get()

        if not doc.exists:
            return jsonify({"error": f"ไม่พบข้อมูลของ user_id: {user_id}"}), 404

        user_data = doc.to_dict()

        # ✅ กำหนดรูปแบบข้อมูลที่จะส่งกลับ
        result = {
            "numimage": user_data.get("numimage", 0),
            "numcall": user_data.get("numcall", 0)
        }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)   
# ---------------- บันทึกการนับภาพ นับการคลิกโทร ----------------
@app.route("/save_count", methods=["POST"])
def save_count():
    try:
        data = request.json
        user_id = data.get("user_id")
        numimage = data.get("numimage", 0)
        numcall = data.get("numcall", 0)

        if not user_id:
            return jsonify({"error": "ต้องระบุ user_id"}), 400

        doc_ref = db.collection("count_process").document(user_id)
        doc_ref.set({
            "numimage": numimage,
            "numcall": numcall
        }, merge=True)  # merge=True จะอัปเดตเฉพาะฟิลด์ที่ส่งมา

        return jsonify({"message": "บันทึกข้อมูลสำเร็จ", "user_id": user_id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)        

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

        doc_ref = db.collection("users").document(user_id)
        doc_ref.set({
            "shop_name": shop_name,
            "user_name": user_name,
            "phone": phone
        })

        #return jsonify({"message": "บันทึก profile สำเร็จ", "id": user_id}), 200
        return jsonify({"message": "บันทึก profile สำเร็จ"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------ ฟังก์ชันคำนวณหลักเลข ------------------------
def get_tens_digit(number: int) -> int:
    return (int(number) // 10) % 10

def get_hundreds_digit(number: int) -> int:
    return (int(number) // 100) % 10

def get_digits(number: int, start: int, end: int) -> int:
    part = int(number) // (10 ** (start - 1))
    return part % (10 ** (end - start + 1))

def get_hundred_thousands_digit(number: int) -> int:
    return (int(number) // 100000) % 10

def update_search_index(index_type, num, user_id, ticket_id):
    if not num:
        print("❌ update_search_index: num ว่าง")
        return
    try:
        db.collection("search_index").document(index_type).collection(str(num)).document(user_id).set({
            ticket_id: True
        })
        print(f"✅ บันทึก {index_type}/{num}/{user_id} สำเร็จ")
    except Exception as e:
        print(f"❌ Firestore error: {e}")


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

        blob = bucket.blob(f"users/{user_id}/imagelottery/{filename}")
        blob.upload_from_filename(filepath)
        blob.make_public()

        image_url = blob.public_url
        ticket_id = str(uuid.uuid4())

        doc_ref = db.collection("users").document(user_id).collection("imagelottery").document(ticket_id)
        doc_ref.set({
            "image_url": image_url,
            "number6": number6,
            "quantity": quantity,
            "created_at": datetime.utcnow()
        })

        number6_int = int(number6)  # แปลงเลขจริง ๆ จาก request

        # ตรวจหลักสิบ หลักร้อย หลักแสน พร้อม log
        for digit_type, func in [("ten", get_tens_digit)]:digit_value = func(number6_int) 
        update_search_index(f"{digit_value}_{digit_type}", number6, user_id, ticket_id)

        for digit_type, func in [("hundreds", get_hundreds_digit)]:digit_value = func(number6_int) 
        update_search_index(f"{digit_value}_{digit_type}", number6, user_id, ticket_id)

        for digit_type, func in [("hundred_thousands", get_hundred_thousands_digit)]:digit_value = func(number6_int) 
        update_search_index(f"{digit_value}_{digit_type}", number6, user_id, ticket_id)

        return jsonify({
            "message": "บันทึกสำเร็จ"
        }), 200

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ------------------- Search Ticket -------------------
 # ------------------- Search Ticket -------------------
@app.route("/search_number", methods=["POST"])
def search_number():
    try:
        data = request.json
        number = data.get("number")

        if not number:
            return jsonify({"error": "ต้องใส่เลขที่ต้องการค้นหา"}), 400

        search_len = len(number)
        index_types = []

        if search_len == 2:
            index_types = ["2_top", "2_bottom"]
        elif search_len == 3:
            index_types = ["3_top", "3_bottom"]
        elif search_len == 6:
            index_types = ["6_exact"]
        else:
            return jsonify({"error": "เลขต้องเป็น 2, 3 หรือ 6 หลัก"}), 400

        results = []
        found_tickets = set()  # เก็บ ticket_id ที่เจอแล้ว

        for digit_type, func in [
            ("ten", get_tens_digit),
            ("hundreds", get_hundreds_digit),
            ("hundred_thousands", get_hundred_thousands_digit)
        ]:
            digit_value = func(int(number))
            index_name = f"{digit_value}_{digit_type}"

            idx_col_ref = db.collection("search_index").document(index_name)
            subcollections = list(idx_col_ref.collections())  # ดึงทุก subcollection

            for subcol in subcollections:
                docs = list(subcol.stream())

                for doc in docs:
                    user_id = doc.id
                    tickets = doc.to_dict()

                    for ticket_id in tickets.keys():
                        if ticket_id in found_tickets:
                            continue  # ข้ามถ้าเจอแล้ว

                        ticket_ref = db.collection("users").document(user_id).collection("imagelottery").document(ticket_id)
                        ticket_doc = ticket_ref.get()

                        if not ticket_doc.exists:
                            continue

                        # ดึงข้อมูลผู้ใช้
                        user_ref = db.collection("users").document(user_id)
                        user_doc = user_ref.get()
                        phone = ""
                        name = ""
                        shop = ""

                        if user_doc.exists:
                            user_data = user_doc.to_dict()
                            phone = user_data.get("phone", "")
                            name = user_data.get("user_name", "")
                            shop = user_data.get("shop_name", "")

                        ticket_data = ticket_doc.to_dict()
                        number6_str = str(ticket_data.get("number6", "")).zfill(6)
                        match_type = None

                        if search_len == 2 and number == number6_str[-2:]:
                            match_type = "2 ตัวล่าง"

                        if search_len == 3 and number == number6_str[:3]:
                            match_type = "3 ตัวบน"

                        if search_len == 3 and number == number6_str[-3:]:
                            match_type = "3 ตัวล่าง"

                        if search_len == 6 and number == number6_str:
                            match_type = "6 ตัวตรง"

                        if match_type:
                            results.append({
                                "user_id": user_id,
                                "ticket_id": ticket_id,
                                "image_url": ticket_data.get("image_url"),
                                "number6": number6_str,
                                "quantity": ticket_data.get("quantity"),
                                "phone": phone,
                                "name": name,
                                "shop": shop,
                                "match_type": match_type
                            })
                            found_tickets.add(ticket_id)

        return jsonify({"results": results}), 200

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

 # ---------------- อ่านข้แมูลจาก firestore แล้วส่งกลับ maui ----------------
@app.route("/get_user", methods=["POST"])
def get_user():
    try: 
        data = request.json
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"error": "กรุณาส่ง user_id"}), 400

        # ดึง document จาก Firestore
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "ไม่พบข้อมูลผู้ใช้"}), 404

        user_data = user_doc.to_dict()

        # เลือกส่งเฉพาะ field ที่ต้องการ
        result = {
            "phone": user_data.get("phone"),
            "shop_name": user_data.get("shop_name"),
            "user_name": user_data.get("user_name")
        }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
#-------------------------------------------

# ------------------- Run -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
