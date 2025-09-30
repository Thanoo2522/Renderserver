import requests
import json
import uuid

# ✅ เปลี่ยนเป็น URL ของ Realtime Database ของคุณเอง
FIREBASE_URL = "https://lotteryview-default-rtdb.asia-southeast1.firebasedatabase.app/users"

def save_user(name):
    user_id = str(uuid.uuid4())
    url = f"{FIREBASE_URL}/{user_id}.json"

    data = {
        "name": name
    }

    response = requests.put(url, data=json.dumps(data))

    if response.status_code == 200:
        print("✅ บันทึกสำเร็จ:", response.json())
    else:
        print("❌ Error:", response.status_code, response.text)

if __name__ == "__main__":
    save_user("สมชาย")
