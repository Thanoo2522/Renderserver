from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)

# อ่าน Internal Database URL จาก Environment Variables ของ Web Service
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("Name")
    phon = data.get("Phon")
    password = data.get("Password")

    if not all([name, phon, password]):
        return jsonify({"success": False, "message": "ข้อมูลไม่ครบ"}), 400

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, phon, password) VALUES (%s, %s, %s)",
            (name, phon, password)   # ❗ production ควรใช้ hash password
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
        cur.execute("SELECT id, name, phon FROM users")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        users = [{"id": r[0], "name": r[1], "phon": r[2]} for r in rows]
        return jsonify(users), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
