
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
from firebase_admin import credentials, storage, firestore
import qrcode
import io
from io import BytesIO
import firebase_admin
from firebase_admin import credentials, firestore
 
 

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
        user_id = data.get("user_id") # user_id = เบอโทรเจ้าของแผง

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
            "numcall": user_data.get("numcall", 0),
            "status": user_data.get("status", 0),
            "Quota": user_data.get("Quota", 0),
            "startdatetime": user_data.get("startdatetime", 0)
        }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)   
# ---------------- บันทึกการนับภาพ นับการคลิกโทร ----------------

# ------------------- Save User Profile -------------------
@app.route("/save_user", methods=["POST"])
def save_user():
    data = request.get_json()
    user_id = data.get("user_id")          # deviceId
    shop_name = data.get("shop_name")
    user_name = data.get("user_name")
    phone = data.get("phone")
    referrer_id = data.get("referrer_id", "")
    register_date = data.get("register_date")

    if not user_id or not phone:
        return jsonify({"error": "user_id และ phone ต้องไม่ว่าง"}), 400

    # ------------------- บันทึก Firestore -------------------
    doc_ref = db.collection("users").document(user_id)
    doc_ref.set({
        "shop_name": shop_name,
        "user_name": user_name,
        "phone": phone,
        "referrer_id": referrer_id,
        "register_date": register_date
    }, merge=True)

    return jsonify({"status": "success"}), 200



# ------------------- Generate QR -------------------
@app.route("/generate_qr", methods=["POST"])
def generate_qr():
    data = request.get_json()
    user_id = data.get("user_id")  # deviceId หรือ phonenum
    if not user_id:
        return jsonify({"error": "user_id ต้องไม่ว่าง"}), 400

    # ------------------- URL สำหรับ QR (Play Store) -------------------
    qr_link = f"https://playstore.link/app?id=your_app_id&ref={user_id}"

    # ------------------- สร้าง QR -------------------
    qr = qrcode.make(qr_link)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # ------------------- บันทึก Firestore -------------------
    doc_ref = db.collection("users").document(user_id)
    doc_ref.set({
        "qr_base64": qr_base64,
        "qr_link": qr_link
    }, merge=True)

    return jsonify({
        "status": "success",
        "qr_base64": qr_base64,
        "qr_link": qr_link
    }), 200

    #-------------------------สร้างด้วยเบอร์โทร-------------------------------------------
@app.route("/create_qr", methods=["POST"])
def create_qr():
    data = request.get_json()
    seller_id = data.get("phone")  # เบอร์โทรผู้ขาย
    link = data.get("link", "https://playstore.link/app?id=123")

    qr = qrcode.make(link)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    doc_ref = db.collection("sellers").document(seller_id)
    doc_ref.set({
        "qr_base64": qr_base64,
        "link": link
    }, merge=True)

    return jsonify({"status": "success", "qr_base64": qr_base64})
    #-----------------------Flask ดึง QR base64 ตามเบอร์โทร----------------------------------
@app.route("/get_qr/<phone>", methods=["GET"])
def get_qr(phone):
    doc_ref = db.collection("sellers").document(phone)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        return jsonify({
            "phone": phone,
            "qr_base64": data.get("qr_base64"),
            "link": data.get("link")
        })
    else:
        return jsonify({"error": "Seller not found"}), 404

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

# ------------------- Update Search Index -------------------
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
# ------------------- Update Search   saller -------------------
def update_search_saller(index_type, num, saller, ticket_id, user_id):
    if not num or not saller:
        print("❌ update_search_saller: ข้อมูลไม่ครบ")
        return
    try:
        db.collection("search_index").document(saller).collection(index_type).document(str(num)).set({
            "ticket_id": ticket_id,
            "user_id": user_id
        })
        print(f"✅ บันทึก {index_type}/{num}/{saller} สำเร็จ")
    except Exception as e:
        print(f"❌ Firestore error: {e}")
       
# ------------------- Save Count -------------------
@app.route("/save_count", methods=["POST"])
def save_count():
    try:
        data = request.get_json(force=True)
        print("📥 รับข้อมูล:", data)

        user_id = data.get("user_id")
        referrer_id = data.get("referrer_id", "")  # optional
        numimage = data.get("numimage")
        numcall = data.get("numcall")
        status = data.get("status", "pass")
        quota = data.get("quota") or data.get("Quota")
        startdatetime = data.get("startdatetime")

        if not user_id:
            return jsonify({"error": "ต้องระบุ user_id"}), 400

        # บันทึก count_process
        doc_ref = db.collection("count_process").document(user_id)
        doc_ref.set({
            "numimage": numimage,
            "numcall": numcall,
            "status": status,
            "Quota": quota,
            "startdatetime": startdatetime,
            "referrer_id": referrer_id
        }, merge=True)

        print("✅ บันทึกสำเร็จ:", user_id, referrer_id, quota, startdatetime)

        # เรียก update_search_index
        update_search_index(user_id, numimage, numcall, referrer_id)

        return jsonify({
            "message": "บันทึกข้อมูลสำเร็จ",
            "user_id": user_id,
            "referrer_id": referrer_id,
            "Quota": quota,
            "startdatetime": startdatetime
        }), 200

    except Exception as e:
        print("❌ SERVER ERROR:", e)
        return jsonify({"error": str(e)}), 500

# ------------------- Run Flask -------------------
if __name__ == "__main__":
    app.run(debug=True)

@app.route("/save_image", methods=["POST"])
def save_image():
    try:
        data = request.json
        user_id = data.get("user_id")
        referrer_id = data.get("referrer_id", "")
        image_base64 = data.get("image_base64")
        number6 = data.get("number6")
        quantity = data.get("quantity")
        priceuse = data.get("priceuse")

        if not user_id or not image_base64 or not number6 or not quantity or not priceuse:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        # แปลงภาพเป็น bytes
        image_bytes = base64.b64decode(image_base64)
        filename = f"{str(uuid.uuid4())}.jpg"
        filepath = os.path.join("/tmp", filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # อัปโหลด Firebase Storage
        blob = bucket.blob(f"lotterypost/{user_id}/imagelottery/{filename}")
        blob.upload_from_filename(filepath)
        blob.make_public()
        image_url = blob.public_url

        # ---------------- สร้าง ticket_id เพียงครั้งเดียว ----------------
        ticket_id = str(uuid.uuid4())

        # บันทึก Firestore
        doc_ref = db.collection("lotterypost").document(user_id).collection("imagelottery").document(ticket_id)
        doc_ref.set({
            "image_url": image_url,
            "number6": number6,
            "quantity": quantity,
            "priceuse": priceuse,
            "referrer_id": referrer_id    # เป็นเบอร์โทรของผู้แนะนำ
        })

        # แปลง number6 เป็น int สำหรับอัปเดต index
        number6_int = int(number6)

        # อัปเดต search index ตามหลักเลข (ใช้ ticket_id เดียวกัน)
        for digit_type, func in [("ten", get_tens_digit),
                                 ("hundreds", get_hundreds_digit),
                                 ("hundred_thousands", get_hundred_thousands_digit)]:
            digit_value = func(number6_int)
            index_id = f"{digit_value}_{digit_type}"

            update_search_index(index_id, number6, user_id, ticket_id)
            update_search_saller(index_id, number6, referrer_id, ticket_id, user_id)
        return jsonify({"message": "บันทึกสำเร็จ"}), 200

    except Exception as e:
        import traceback
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500



# ------------------- Search Number -------------------
@app.route("/search_number_priority", methods=["POST"])
def search_number_priority():
    try:
        data = request.json
        number = data.get("number")
        saller = data.get("saller")  # เช่น เบอร์โทรของผู้ขาย / referrer_id
        max_results = 100

        if not number:
            return jsonify({"error": "ต้องใส่เลขที่ต้องการค้นหา"}), 400

        search_len = len(number)
        if search_len not in [2, 3, 6]:
            return jsonify({"error": "เลขต้องเป็น 2, 3 หรือ 6 หลัก"}), 400

        results = []
        found_tickets = set()

        # --------------------
        # 1️⃣ ค้นจากสายผู้แนะนำก่อน
        # --------------------
        if saller:
            saller_ref = db.collection("search_index").document(saller)
            saller_collections = list(saller_ref.collections())

            for subcol in saller_collections:
                for doc in subcol.stream():
                    doc_data = doc.to_dict()
                    user_id = doc_data.get("user_id")
                    ticket_id = doc_data.get("ticket_id")
                    if not user_id or not ticket_id:
                        continue

                    ticket_ref = db.collection("lotterypost").document(user_id).collection("imagelottery").document(ticket_id)
                    ticket_doc = ticket_ref.get()
                    if not ticket_doc.exists:
                        continue

                    ticket_data = ticket_doc.to_dict()
                    number6_str = str(ticket_data.get("number6", "")).zfill(6)

                    # ตรวจจับรูปแบบการตรง
                    match_type = get_match_type(number, number6_str, search_len)
                    if match_type:
                        results.append({
                            "user_id": user_id,
                            "ticket_id": ticket_id,
                            "image_url": ticket_data.get("image_url"),
                            "number6": number6_str,
                            "quantity": ticket_data.get("quantity"),
                            "seller": saller,
                            "match_type": match_type
                        })
                        found_tickets.add(ticket_id)

                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

        # --------------------
        # 2️⃣ ถ้ายังไม่ครบ 100 ให้ไปค้นจาก index หลัก
        # --------------------
        if len(results) < max_results:
            # คำนวณชื่อ index ตามหลักเลข (2 ตัว / 3 ตัว / 6 ตัว)
            index_name = get_index_name(number)
            idx_ref = db.collection("search_index").document(index_name)

            # รวมทุก subcollection ใน index หลัก
            for subcol in idx_ref.collections():
                for doc in subcol.stream():
                    doc_data = doc.to_dict()
                    user_id = doc_data.get("user_id")
                    ticket_id = doc_data.get("ticket_id")
                    if not user_id or not ticket_id:
                        continue
                    if ticket_id in found_tickets:
                        continue

                    ticket_ref = db.collection("lotterypost").document(user_id).collection("imagelottery").document(ticket_id)
                    ticket_doc = ticket_ref.get()
                    if not ticket_doc.exists:
                        continue

                    ticket_data = ticket_doc.to_dict()
                    number6_str = str(ticket_data.get("number6", "")).zfill(6)
                    match_type = get_match_type(number, number6_str, search_len)
                    if match_type:
                        results.append({
                            "user_id": user_id,
                            "ticket_id": ticket_id,
                            "image_url": ticket_data.get("image_url"),
                            "number6": number6_str,
                            "quantity": ticket_data.get("quantity"),
                            "seller": ticket_data.get("referrer_id", ""),
                            "match_type": match_type
                        })
                        found_tickets.add(ticket_id)

                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

        return jsonify({"results": results[:max_results]}), 200

    except Exception as e:
        import traceback
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# -------------------
# 🔧 Helper functions
# -------------------
def get_match_type(search, number6, length):
    if length == 2 and search == number6[-2:]:
        return "2 ตัวล่าง"
    elif length == 3 and search == number6[:3]:
        return "3 ตัวบน"
    elif length == 3 and search == number6[-3:]:
        return "3 ตัวล่าง"
    elif length == 6 and search == number6:
        return "6 ตัวตรง"
    return None


def get_index_name(number):
    n = int(number)
    if len(number) == 2:
        return f"{n}_ten"
    elif len(number) == 3:
        return f"{n}_hundreds"
    elif len(number) == 6:
        return f"{n}_hundred_thousands"
    else:
        return "unknown"


#------------------------- อ่าน firestoreไปแสดงที่หน้า UI shopview ------
@app.route("/get_tickets_by_user", methods=["POST"])
def get_tickets_by_user():
    try:
        data = request.json
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"error": "missing user_id"}), 400

        tickets_ref = db.collection("lotterypost").document(user_id).collection("imagelottery")
        tickets = list(tickets_ref.stream())

        results = []
        for t in tickets:
            t_data = t.to_dict()
            results.append({
                "ticket_id": t.id,
                "image_url": t_data.get("image_url", ""),
                "number6": str(t_data.get("number6", "")).zfill(6),
                "quantity": int(t_data.get("quantity", 0)),
                "priceuse": float(t_data.get("priceuse", 0)),  # ✅ บังคับให้เป็น number
            })

        return jsonify({"results": results}), 200

    except Exception as e:
        print("❌ Error:", e)
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
#-------------------------------บันทึกการโอนเงิน ------------
@app.route("/save_payment", methods=["POST"])
def save_payment():
    try:
        data = request.get_json()

        # ตรวจสอบข้อมูลที่ส่งมา
        namebookbank = data.get("namebookbank")
        namphone = data.get("namphone")
        date = data.get("date")
        time = data.get("time")
        money = data.get("money")

        # 🔒 ปลอดภัยสำหรับ document ID
        safe_date = date.replace("/", "-")      # -> "10-10-68"
        safe_time = time.replace(":", "-")      # -> "12-02-15"
        doc_id = f"{safe_date},{safe_time}"     # -> "10-10-68,12-02-15"

        # ตรวจสอบว่ามีทุก field หรือไม่
        if not all([namebookbank,namphone, date, time, money]):
            return jsonify({"error": "Missing required fields"}), 400

        # 📝 สร้าง document ใหม่ใน Firestore
        doc_ref = db.collection("moneytranfer").document(doc_id)
        doc_ref.set({
            "namebookbank": namebookbank,
            "namphone": namphone,
            "date": date,
            "time": time,
            "money": money
        })

        return jsonify({"message": "Data saved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)


# ------------------- Run -------------------save_image
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
