import requests
import time

# 把這裡換成你剛剛找到的真實 Firebase 網址
MY_UID = "4x5rweovlhaGIdxf4NEG3bqnfjf1"
firebase_url = f"https://smart-timer-app-7da95-default-rtdb.firebaseio.com/users/{MY_UID}/notifications.json"

# 模擬當前時間
time_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

# 完全模擬 ESP32 遇到過熱時打包的資料
alert_payload = {
    "title": "危險！溫度過高",
    "content": "系統已強制切斷電源以保護設備安全。(模擬測試)",
    "type": "read",
    "status": "unread",
    "temperature": "20.8",
    "zone_name": "0312",
    "timestamp": time_str
}

try:
    print("發送假警報中...")
    res = requests.post(firebase_url, json=alert_payload)
    print("✅ 模擬警報已發送！狀態碼:", res.status_code)
    print("趕快打開你的 Flutter App 看看有沒有跳出暗紅色警告！")
except Exception as e:
    print("發送失敗:", e)