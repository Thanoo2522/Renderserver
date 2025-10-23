
from flask import Flask, request, jsonify, send_from_directory
import os
import base64
from datetime import datetime
import traceback
from openai import OpenAI
import uuid
import json
import time
import requests
import firebase_admin
import logging
from datetime import datetime
from firebase_admin import credentials, storage, firestore
import re   # ✅ เพิ่มบรรทัดนี้!
 
 

app = Flask(__name__)

# ------------------- Config -------------------get_user
FIREBASE_URL = "https://lotteryview-default-rtdb.asia-southeast1.firebasedatabase.app/users"
BUCKET_NAME = "lotteryview.firebasestorage.app"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

service_account_json = os.environ.get("FIREBASE_SERVICE_KEY")
#--------------------------------
 
#-------------------------------
#if not service_account_json:
 #   raise Exception("❌ Environment variable FIREBASE_SERVICE_KEY not set")

cred = credentials.Certificate(json.loads(service_account_json))
firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})

db = firestore.client()
bucket = storage.bucket()

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
        model="gpt-4o-mini",  # ใช้ GPT-4o-mini (Vision)
        messages=[
            {"role": "system", "content": "คุณเป็นผู้ช่วยวิเคราะห์ภาพสลากกินแบ่งรัฐบาล ให้ตอบเฉพาะ JSON เท่านั้น"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        temperature=0.1,  # ลดความสุ่มของคำตอบ
    )

    raw_answer = response.choices[0].message.content.strip()

    # ✅ ตัดเฉพาะส่วน JSON (ป้องกัน GPT พูดเกิน)
    first_brace = raw_answer.find("{")
    last_brace = raw_answer.rfind("}")
    if first_brace != -1 and last_brace != -1:
        raw_answer = raw_answer[first_brace:last_brace+1]

    return raw_answer

#--------------------- เช็คการเชื่อมต่อ firebas ----------
@app.route("/check_firebase", methods=["GET"])
def check_firebase():
    try:
        bucket = storage.bucket()
        # ทดสอบ list ไฟล์ (เช็คว่าเชื่อมต่อได้จริง)
        blobs = list(bucket.list_blobs(max_results=1))
        return jsonify({"status": "connected", "bucket": BUCKET_NAME})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
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

#-----------------------update_status ของแแผงลอตเตอร์รี่  ----------------------------------
@app.route("/update_status", methods=["POST"])
def update_status():
    try:
        data = request.get_json()
        user_id = data["userId"]
        status = data["status"]  # "active" หรือ "nonactive"

        doc_ref = db.collection("users").document(user_id)
        doc_ref.update({"status": status})

        return jsonify({"status": "success", "message": f"User {user_id} updated to {status}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    
 #------------------- อ่านเฉพาะ field” -------------------------------------------------   
@app.route("/get_field", methods=["POST"])
def get_field():
    try:
        data = request.get_json()
        user_id = data["userId"]
        field_name = data["fieldName"]  # เช่น "status"

        doc_ref = db.collection("users").document(user_id)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({"status": "error", "message": "Document not found"}), 404

        doc_data = doc.to_dict()
        if field_name not in doc_data:
            return jsonify({"status": "error", "message": f"Field '{field_name}' not found"}), 404

        return jsonify({
            "status": "success",
            "field": field_name,
            "value": doc_data[field_name]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    #----------------------------- อ่านค่า Quota , date--------------
@app.route("/get_user_data", methods=["POST"])
def get_user_data():
    try:
        data = request.get_json()
        user_id = data.get("user_id")  # เช่น "1234"

        # อ่าน document จาก Firestore
        doc_ref = db.collection("users").document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            user_data = doc.to_dict()
            return jsonify({
               "data": user_data.get("data"),  # อ่านวันที่
                "Quota": user_data.get("Quota")
    
            })
        else:
            return jsonify({"status": "error", "message": "User not found"}), 404

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
 
# ------------------- Save User Profile -------------------get_count
@app.route("/save_user", methods=["POST"])
def save_user():
    try:
        data = request.json
        user_id = data.get("user_id")
        shop_name = data.get("shop_name")
        user_name = data.get("user_name")
        phone = data.get("phone")

        numiage = data.get("numiage")
        numcall = data.get("numcall")       
        
        Quota = data.get("Quota") 
        startdate = data.get("startdate")  

        if not shop_name or not user_name or not phone:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        if not user_id:
            user_id = str(uuid.uuid4())

        doc_ref = db.collection("users").document(user_id)
        doc_ref.set({
            "shop_name": shop_name,
            "user_name": user_name,
            "phone": phone,
             "Quota": Quota,
              "startdate": startdate,
              "numiage": numiage,
              "numcall":numcall

            

        })

        #return jsonify({"message": "บันทึก profile สำเร็จ", "id": user_id}), 200
        return jsonify({"message": "บันทึก profile สำเร็จ"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ------------------- Save promission-------------------
@app.route("/promis", methods=["POST"])
def promis():
    try:
        data = request.json
        promission = data.get("promission")
        phone = data.get("phone")
        

        if not promission or not phone:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        if not promission:
            promission = str(uuid.uuid4())

        doc_ref = db.collection("controlpromission").document(phone)
        doc_ref.set({
            "promission": promission
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

#-------------------------------------------------------------------------------------
@app.route("/save_image", methods=["POST"])
def save_image():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        image_base64 = data.get("image_base64")
        number6 = data.get("number6")
        quantity = data.get("quantity")
        datetime_str = data.get("datetime")

        # ✅ ตรวจสอบข้อมูลครบ
        if not all([user_id, image_base64, number6, quantity]):
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        # ✅ แปลง base64 → ไฟล์ภาพ
        image_bytes = base64.b64decode(image_base64)
        filename = f"{uuid.uuid4()}.jpg"
        filepath = os.path.join("/tmp", filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # ✅ อัปโหลดขึ้น Firebase Storage
        blob = bucket.blob(f"users/{user_id}/imagelottery/{filename}")
        blob.upload_from_filename(filepath)
        blob.make_public()
        image_url = blob.public_url

        # ✅ สร้าง document ใหม่ใน Firestore
        ticket_id = str(uuid.uuid4())
        doc_ref = db.collection("users").document(user_id).collection("imagelottery").document(ticket_id)
        doc_ref.set({
            "image_url": image_url,
            "number6": number6,
            "quantity": quantity,
            "datetime": datetime_str,
            "created_at": datetime.utcnow()
        })

        # ✅ อัปเดต search index (เลขหลักสิบ, ร้อย, แสน)
        try:
            number6_int = int(number6)
            update_search_index(f"{get_tens_digit(number6_int)}_ten", number6, user_id, ticket_id)
            update_search_index(f"{get_hundreds_digit(number6_int)}_hundreds", number6, user_id, ticket_id)
            update_search_index(f"{get_hundred_thousands_digit(number6_int)}_hundred_thousands", number6, user_id, ticket_id)
        except ValueError:
            print("⚠️ number6 ไม่ใช่ตัวเลขล้วน (skip update index)")

        return jsonify({
            "message": "บันทึกสำเร็จ",
            "image_url": image_url
        }), 200

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ------------------- บันทึกแจ้งการโอนเงิน -------------------
@app.route("/save_payment", methods=["POST"])
def save_payment():
    try:
        data = request.get_json()

        # ตรวจสอบข้อมูลที่ส่งมา
        namebookbank = data.get("namebookbank")
        date = data.get("date")
        time = data.get("time")
        status = data.get("status")

        # 🔒 ปลอดภัยสำหรับ document ID
        safe_date = date.replace("/", "-")      # -> "10-10-68"
        safe_time = time.replace(":", "-")      # -> "12-02-15"
        doc_id = f"{safe_date},{safe_time}"     # -> "10-10-68,12-02-15"

        # ตรวจสอบว่ามีทุก field หรือไม่
        if not all([namebookbank, date, time, status]):
            return jsonify({"error": "Missing required fields"}), 400

        # 📝 สร้าง document ใหม่ใน Firestore
        doc_ref = db.collection("users").document(doc_id)
        doc_ref.set({
            "namebookbank": namebookbank,
            "date": date,
            "time": time,
            "status": status
        })

        return jsonify({"message": "Data saved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

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
            "user_name": user_data.get("user_name"),

            "numimage": user_data.get("numimage"),
            "numcall": user_data.get("numcall"),

             "Quota": user_data.get("Quota"), 
             "startdate": user_data.get("startdate")   
       
        }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
#------------ขขขขขขขขขขขขขขขขขขขขขขขขขขขขขขขขขขขข
@app.route("/sms_to_firestore", methods=["POST"])
def sms_to_firestore():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        sender = data.get("sender")
        message = data.get("message")

        if not sender or not message:
            return jsonify({"status": "error", "message": "Missing fields"}), 400

        logging.info(f"Received SMS from {sender}: {message}")

        # บันทึกลง Firestore
        # สมมติ collection ชื่อ "bank_sms"
        doc_ref = db.collection("bank_sms").document(sender)
        doc_ref.set({
            "last_message": message,
            "timestamp": firestore.SERVER_TIMESTAMP
        }, merge=True)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logging.exception("Error in /sms_to_firestore")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # สำหรับ test local
    app.run(host="0.0.0.0", port=5000, debug=True)
# --------------------------- SAVE SMS ---------------------------
@app.route("/save_sms", methods=["POST"])
def save_sms():
    try:
        data = request.json
        device_id = data.get("deviceId")
        message = data.get("message")

        if not device_id or not message:
            return jsonify({"error": "deviceId or message missing"}), 400

        # 🔹 สร้างชื่อ field ใหม่ เช่น sms_20251020095030
        field_key = datetime.utcnow().strftime("sms_%Y%m%d%H%M%S")

        # 🔹 บันทึกข้อมูลลง Firestore
        doc_ref = db.collection("bank_sms").document(device_id)
        doc_ref.set({
            field_key: {                
                "raw_message": message
            },
            "last_message": message
        }, merge=True)

        logging.info(f"✅ Saved SMS to {device_id} : {field_key}")

        return jsonify({
            "status": "success",
            "field_key": field_key,
            "saved_message": message
        }), 200

    except Exception as e:
        logging.error(f"🔥 Error saving SMS: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --------------------------- GET SMS FIELDS ---------------------------
@app.route("/get_sms_fields/<device_id>", methods=["GET"])
def get_sms_fields(device_id):
    try:
        doc_ref = db.collection("bank_sms").document(device_id)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({"error": "device not found"}), 404

        data = doc.to_dict()

        # 🔹 ดึงเฉพาะ field last_message
        last_message = data.get("last_message", "")

        return jsonify({
            "device_id": device_id,
            "last_message": last_message
        }), 200

    except Exception as e:
        logging.error(f"🔥 Error getting last_message: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --------------------------- MAIN ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
# ------------------- Run -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
