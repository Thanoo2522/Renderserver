from flask import Flask, request, jsonify, send_from_directory
import os
import base64
from datetime import datetime
import traceback
from openai import OpenAI

import uuid
import json
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
if not service_account_json:
    raise Exception("❌ Environment variable FIREBASE_SERVICE_KEY not set")

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

        doc_ref = db.collection("users").document(user_id)
        doc_ref.set({
            "shop_name": shop_name,
            "user_name": user_name,
            "phone": phone
        })

        return jsonify({"message": "บันทึก profile สำเร็จ", "id": user_id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------- Save Image + Ticket -------------------
@app.route("/save_image", methods=["POST"])
def save_image():
    try:
        data = request.json
        user_id = data.get("user_id")
        image_base64 = data.get("image_base64")
        #number6 = str(data.get("number6")).strip()
        number6 = data.get("number6")
        quantity = data.get("quantity")

        if not user_id or not image_base64 or not number6 or not quantity:
            return jsonify({"error": "ข้อมูลไม่ครบ"}), 400

        # -------------------------------------------
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

        # -------------------------------------------
        doc_ref = db.collection("users").document(user_id).collection("imagelottery").document(ticket_id)
        doc_ref.set({
            "image_url": image_url,
            "number6": number6,
            "quantity": quantity,
            "created_at": datetime.utcnow()
        })
        #------------------หาหลักสิบ ------------------------
        def get_tens_digit(number: int) -> int: 
         return (number // 10) % 10
        #---------------- หาหลักร้อย , 3ตัวท้าย-------------------------
        def get_hundreds_digit(number: int) -> int:
         return (number // 100) % 10
        #---------------3ตัวหน้า------------------------------------
        def get_digits(number: int, start: int, end: int) -> int:
        # ตัดเลขที่เกินด้านขวาทิ้งก่อน
         part = number // (10 ** (start - 1))
         # เอาเฉพาะส่วนที่ต้องการ
         return part % (10 ** (end - start + 1))
        #----------------หาหลักแสน--------------------------
        def get_hundred_thousands_digit(number: int) -> int:
         return (number // 100000) % 10
        # ---------------- Update Search Index ----------------
        def update_search_index(index_type, num, user_id, ticket_id):
            if not num:
                return
            db.collection("search_index").document(index_type).collection(num).document(user_id).set({
                ticket_id: True
            })
        if get_tens_digit(int.number6)==0:update_search_index("0_ten", number6, user_id, ticket_id) # หลักสิบเป็น 0
        if get_tens_digit(int.number6)==1:update_search_index("1_ten", number6, user_id, ticket_id) # หลักสิบเป็น 1
        if get_tens_digit(int.number6)==2:update_search_index("2_ten", number6, user_id, ticket_id) # หลักสิบเป็น 2
        if get_tens_digit(int.number6)==3:update_search_index("3_ten", number6, user_id, ticket_id) # หลักสิบเป็น 3
        if get_tens_digit(int.number6)==4:update_search_index("4_ten", number6, user_id, ticket_id) # หลักสิบเป็น 4
        if get_tens_digit(int.number6)==5:update_search_index("5_ten", number6, user_id, ticket_id) # หลักสิบเป็น 5
        if get_tens_digit(int.number6)==6:update_search_index("6_ten", number6, user_id, ticket_id) # หลักสิบเป็น 6
        if get_tens_digit(int.number6)==7:update_search_index("7_ten", number6, user_id, ticket_id) # หลักสิบเป็น 7
        if get_tens_digit(int.number6)==8:update_search_index("8_ten", number6, user_id, ticket_id) # หลักสิบเป็น 8
        if get_tens_digit(int.number6)==9:update_search_index("9_ten", number6, user_id, ticket_id) # หลักสิบเป็น 9

        if get_hundreds_digit(int.number6)==0:update_search_index("0_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 0
        if get_hundreds_digit(int.number6)==1:update_search_index("1_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 1
        if get_hundreds_digit(int.number6)==2:update_search_index("2_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 2
        if get_hundreds_digit(int.number6)==3:update_search_index("3_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 3
        if get_hundreds_digit(int.number6)==4:update_search_index("4_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 4
        if get_hundreds_digit(int.number6)==5:update_search_index("5_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 5
        if get_hundreds_digit(int.number6)==6:update_search_index("6_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 6
        if get_hundreds_digit(int.number6)==7:update_search_index("7_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 7
        if get_hundreds_digit(int.number6)==8:update_search_index("8_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 8
        if get_hundreds_digit(int.number6)==9:update_search_index("9_hundreds", number6, user_id, ticket_id) # หลักร้อยเป็น 9

        if get_hundred_thousands_digit(int.number6)==0:update_search_index("0_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 0
        if get_hundred_thousands_digit(int.number6)==1:update_search_index("1_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 1
        if get_hundred_thousands_digit(int.number6)==2:update_search_index("2_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 2
        if get_hundred_thousands_digit(int.number6)==3:update_search_index("3_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 3
        if get_hundred_thousands_digit(int.number6)==4:update_search_index("4_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 4
        if get_hundred_thousands_digit(int.number6)==5:update_search_index("5_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 5
        if get_hundred_thousands_digit(int.number6)==6:update_search_index("6_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 6
        if get_hundred_thousands_digit(int.number6)==7:update_search_index("7_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 7
        if get_hundred_thousands_digit(int.number6)==8:update_search_index("8_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 8
        if get_hundred_thousands_digit(int.number6)==9:update_search_index("9_hundred_thousands", number6, user_id, ticket_id) # หลักแสนเป็น 9
        

         

        return jsonify({
            "message": "บันทึกสำเร็จ",
            "ticket_id": ticket_id,
            "image_url": image_url
        }), 200

    except Exception as e:
        print("❌ SERVER ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ------------------- Search Ticket -------------------
@app.route("/search_number", methods=["POST"])
def search_number():
    try:
        data = request.json
        number = str(data.get("number")).strip()

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

        for idx in index_types:
            idx_col = db.collection("search_index").document(idx).collection(number)
            docs = idx_col.stream()

            for doc in docs:
                user_id = doc.id
                tickets = doc.to_dict()

                for ticket_id in tickets.keys():
                    ticket_ref = db.collection("users").document(user_id).collection("imagelottery").document(ticket_id)
                    ticket_doc = ticket_ref.get()
                    if not ticket_doc.exists:
                        continue

                    ticket_data = ticket_doc.to_dict()
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
