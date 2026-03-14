import urequests, ujson
import xtools, utime
from machine import Pin
import config
from umqtt.simple import MQTTClient
import ntptime # 內建的網路對時模組

# --- 1. 硬體與全域變數設定 ---
MY_ZONE_ID = "-OnUj2PeTETiwglVVhB1" # 記得換成你的
MY_DEVICE_ID = "2"

relay = Pin(5, Pin.OUT)
relay.value(0) # 預設關閉

current_schedule = None # 儲存目前的排程 JSON
current_state = False   # 儲存目前的繼電器狀態 (避免重複發送 MQTT)

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
    global current_schedule
    try:
        payload = ujson.loads(msg.decode())
        
        # 檢查是不是給我的指令
        if payload.get("device_id") == MY_DEVICE_ID:
            print("收到排程訊息:", payload)
            
            if payload.get("action") == "cancel":
                current_schedule = None
                print(">>> 排程已清空")
            else:
                current_schedule = payload
                print(">>> 排程已更新")
                
    except Exception as e:
        print("JSON 解析失敗:", e)

client.set_callback(sub_cb)
client.connect()

topic = "smart_timer/schedule"
print("訂閱頻道:", topic)
client.subscribe(topic)

# --- 4. 輔助函式：發送狀態 ---
def update_status(is_active):
    global current_state
    current_state = is_active
    relay.value(1 if is_active else 0) # 驅動繼電器
    
    status_payload = {
        "zone_id": MY_ZONE_ID,
        "device_id": MY_DEVICE_ID,
        "is_active": is_active
    }
    
    try:
        client.publish("smart_timer/status", ujson.dumps(status_payload))
        print(f"發送狀態更新 -> is_active: {is_active}")
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
    
    if current_schedule is not None:
        mode = current_schedule.get("mode")
        start_str = current_schedule.get("start", "")
        end_str = current_schedule.get("end", "")
        
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
                date_str = current_schedule.get("date", "")
                if date_str:
                    y, m, d = map(int, date_str.split('-'))
                    if now[0] == y and now[1] == m and now[2] == d:
                        is_day_match = True
                        
            elif mode == "repeat":
                days = current_schedule.get("days", [])
                weekday = now[6] # MicroPython 的 weekday 剛好跟我們 App 的 List 順序一致！
                if len(days) == 7 and days[weekday] == True:
                    is_day_match = True
            
            # 3. 綜合判斷：現在到底該不該通電？
            should_be_active = (is_time_match and is_day_match)
            
            # 4. 狀態改變才做事 (避免每秒瘋狂發送 MQTT)
            if should_be_active and not current_state:
                update_status(True)
            elif not should_be_active and current_state:
                update_status(False)

    utime.sleep(1)