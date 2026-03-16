import urequests, ujson
import xtools, utime
from machine import Pin
import config
from umqtt.simple import MQTTClient
import ntptime # 內建的網路對時模組

# --- 1. 硬體與全域變數設定 ---
MY_UID = "4x5rweovlhaGIdxf4NEG3bqnfjf1"
MY_ZONE_ID = "-OnUj2PeTETiwglVVhB1"

my_devices = {
    "2":        {"pin": Pin(5, Pin.OUT),  "state": False, "schedule": None},
    "0312_test1": {"pin": Pin(4, Pin.OUT),  "state": False, "schedule": None},
    #"fan_01":   {"pin": Pin(14, Pin.OUT), "state": False, "schedule": None}
}

# 預設把所有設備都關閉
for dev_id, dev_data in my_devices.items():
    dev_data["pin"].value(0)

# --- 2. 網路與對時 ---
xtools.connect_wifi_led() # 沿用你工具包的連線方式

try:
    print("同步網路時間 (NTP)...")
    ntptime.settime() # 抓取 UTC 時間存入晶片
    print("對時成功！")
except Exception as e:
    print("對時失敗，請重啟或檢查網路", e)

# 台灣時間 UTC+8 (將秒數加上去)
UTC_OFFSET = 8 * 3600

# --- 3. MQTT 設定與回撥 ---
client = MQTTClient(
    client_id = xtools.get_id(),
    server = "broker.hivemq.com",
    ssl = False,
)

def sub_cb(topic, msg):
    try:
        topic_str = topic.decode('utf-8') # 先把頻道名稱解碼成字串
        payload = ujson.loads(msg.decode('utf-8'))
        dev_id = payload.get("device_id")
        
        # 檢查這個設備 ID 是不是歸這塊 ESP32 管的
        if dev_id in my_devices:
            print(f"\n📥 [收到頻道] {topic_str}")
            print(f"✨ 收到專屬設備 [{dev_id}] 的排程指令！")
            
            if payload.get("action") == "cancel":
                my_devices[dev_id]["schedule"] = None
                print(f">>> [{dev_id}] 排程已清空")
            else:
                my_devices[dev_id]["schedule"] = payload
                print(f">>> [{dev_id}] 排程已更新")
                
    except Exception as e:
        print("JSON 解析失敗:", e)

client.set_callback(sub_cb)
client.connect()

topic_sub = f"users/{MY_UID}/zones/{MY_ZONE_ID}/devices/+/schedule"
client.subscribe(topic_sub.encode('utf-8'))
print(f"👂 開始監聽區域專屬頻道: {topic_sub}")

# --- 4. 輔助函式：發送狀態 ---
def update_status(dev_id, is_active):
    my_devices[dev_id]["state"] = is_active
    my_devices[dev_id]["pin"].value(1 if is_active else 0)
    
    status_payload = {
        "zone_id": MY_ZONE_ID,
        "device_id": dev_id,
        "is_active": is_active
    }
    
    try:
        client.publish("smart_timer/status", ujson.dumps(status_payload))
        print(f"📤 [狀態回報] 設備 {dev_id} -> {'開啟' if is_active else '關閉'}")
    except Exception as e:
        print("狀態發送失敗:", e)

# --- 5. 主迴圈 ---
print("--- 系統開始運行 ---")
while True:
    # 接收 MQTT 訊息
    client.check_msg()
    
    # 計算當地時間
    # now 的格式: (年, 月, 日, 時, 分, 秒, 星期幾, 一年的第幾天)
    # 注意: 星期幾是 0-6 (0=星期一, 6=星期日)
    now = utime.localtime(utime.time() + UTC_OFFSET)
    now_mins = now[3] * 60 + now[4]
    
    for dev_id, dev_data in my_devices.items():
        schedule = dev_data["schedule"]
        
        if schedule is not None:
            mode = schedule.get("mode")
            start_str = schedule.get("start", "")
            end_str = schedule.get("end", "")
        
            if start_str and end_str:
                # 解析時間字串 (例如 "18:30" 轉成分鐘數方便比對)
                sh, sm = map(int, start_str.split(':'))
                eh, em = map(int, end_str.split(':'))
                
                now_mins = now[3] * 60 + now[4]
                start_mins = sh * 60 + sm
                end_mins = eh * 60 + em
                
                # 1. 判斷時間是否吻合
                is_time_match = (start_mins <= now_mins < end_mins)
                
                # 2. 判斷日期是否吻合
                is_day_match = False
                
                if mode == "once":
                    date_str = schedule.get("date", "")
                    if date_str:
                        y, m, d = map(int, date_str.split('-'))
                        if now[0] == y and now[1] == m and now[2] == d:
                            is_day_match = True
                            
                elif mode == "repeat":
                    days = schedule.get("days", [])
                    weekday = now[6] # MicroPython 的 weekday 剛好跟我們 App 的 List 順序一致！
                    if len(days) == 7 and days[weekday] == True:
                        is_day_match = True
                
                # 3. 綜合判斷：現在到底該不該通電？
                should_be_active = (is_time_match and is_day_match)
                
                # 4. 狀態改變才做事 (避免每秒瘋狂發送 MQTT)
                if should_be_active and not dev_data["state"]:
                    update_status(dev_id, True)
                elif not should_be_active and dev_data["state"]:
                    update_status(dev_id, False)

    utime.sleep(1)