from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash
import psycopg2
import os

app = Flask(__name__)
CORS(app)  # ✅ อนุญาต cross-origin จาก client app

DATABASE_URL = os.environ.get("BASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("name")
    phone = data.get("phone")
    password = data.get("password")

    if not all([name, phone, password]):
        return jsonify({"success": False, "message": "ข้อมูลไม่ครบ"}), 400

    try:
        hashed_password = generate_password_hash(password)  # ✅ hash password
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, phone, password) VALUES (%s, %s, %s)",
            (name, phone, hashed_password)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True, "message": "สมัครสมาชิกสำเร็จ"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/users", methods=["GET"])
def get_users():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, name, phone FROM users ORDER BY id DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        users = [{"id": r[0], "name": r[1], "phone": r[2]} for r in rows]
        return jsonify(users), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
