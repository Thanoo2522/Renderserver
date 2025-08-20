from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)

# อ่าน connection string จาก environment variables
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", 5432)
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

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
            "INSERT INTO Users (Name, Phon, Password) VALUES (%s, %s, %s)",
            (name, phon, password)  # production ควร hash password
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True, "message": "สมัครสมาชิกสำเร็จ"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
