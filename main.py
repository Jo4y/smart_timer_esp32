import urequests, ujson
import xtools, utime
from machine import Pin
#import config
from umqtt.simple import MQTTClient
import ntptime # 內建的網路對時模組
import ds_sensor, time
import pzem_test
# import pzem004t

#測試版
power_meter = pzem_test.PZEM(uart_id=1, tx_pin=9, rx_pin=8)
print("電量計初始化完成！")

# 引用版
# pzem_uart = UART(1, baudrate=9600, tx=Pin(10), rx=Pin(9))
# power_meter = pzem004t.PZEM(pzem_uart)

if ds_sensor.init_sensor(2):
    print("溫度感測器OK！")

# --- 1. 硬體與全域變數設定 ---
MY_UID = "4x5rweovlhaGIdxf4NEG3bqnfjf1"
MY_ZONE_ID = "-OnUj2PeTETiwglVVhB1"

my_devices = {
    "2":        {"pin": Pin(3, Pin.OUT),  "state": False, "schedule": None},
    "0312_test1": {"pin": Pin(4, Pin.OUT),  "state": False, "schedule": None},
}

# 預設把所有設備都關閉
for dev_id, dev_data in my_devices.items():
    dev_data["pin"].value(0)

# --- 2. 網路與對時 ---
print("開始網路初始化...")
xtools.auto_connect()

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
        
TEMP_REPORT_INTERVAL = 20000 # 60000 毫秒 = 60 秒回報一次
last_temp_report = utime.ticks_ms()

# --- 5. 主迴圈 ---
print("--- 系統開始運行 ---")
while True:
    # 接收 MQTT 訊息
    client.check_msg()
    
    # 計算當地時間
    # now 的格式: (年, 月, 日, 時, 分, 秒, 星期幾, 一年的第幾天)
    # 星期幾是 0-6 (0=星期一, 6=星期日)
    now = utime.localtime(utime.time() + UTC_OFFSET)
    now_mins = now[3] * 60 + now[4]
    
    #溫度回報
    current_time = utime.ticks_ms()
    if utime.ticks_diff(current_time, last_temp_report) >= TEMP_REPORT_INTERVAL:
        temp = ds_sensor.get_temp()
        if temp is not None:
            print(f"🌡️現在溫度是 {temp:.1f} °C，準備上傳！")
            
            # 過熱緊急斷電防線
            SAFE_TEMP_LIMIT = 30.0  # 假設安全上限為 30 度
            
            if temp >= SAFE_TEMP_LIMIT:
                print(f"🚨🚨🚨 警告！溫度飆達 {temp:.1f}°C，啟動緊急斷電！ 🚨🚨🚨")
                
                # 1. 強制關閉所有歸這塊板子管的繼電器
                for dev_id, dev_data in my_devices.items():
                    if dev_data["state"]: # 如果插座現在是開著的
                        update_status(dev_id, False) # 呼叫原本寫好的函式，斷電並回報狀態
                        # 同時清空該設備的排程，防止它下一秒又因為排程時間到了被自動打開
                        my_devices[dev_id]["schedule"] = None 
                firebase_url = f"https://smart-timer-app-7da95-default-rtdb.firebaseio.com/users/{MY_UID}/notifications.json"
                
                # 取得目前時間並組裝格式
                y, m, d, h, minute, s, _, _ = utime.localtime(utime.time() + UTC_OFFSET)
                time_str = f"{y}-{m:02d}-{d:02d}T{h:02d}:{minute:02d}:{s:02d}"
                
                # 2. 發送專屬的「警報訊息」給 App (MQTT 廣播)
                alert_payload = {
                    "title": "危險！溫度過高",
                    "content": "系統已強制切斷電源以保護設備安全。",
                    "type": "danger",
                    "status": "unread",
                    "temperature": round(temp, 1),
                    "zone_name": "我的智慧空間",
                    "timestamp": time_str
                }
                
                try:
                    res = urequests.post(firebase_url, json=alert_payload)
                    print("📤 [過熱警報] 已成功寫入 Firebase 通知中心！")
                    res.close()
                except Exception as e:
                    print("警報寫入 Firebase 失敗:", e)
                    
             # --- 讀取輕量版 PZEM 數據 ---
            power_data = power_meter.read_data()
            power_state_str = "safe" # 預設安全
            
            update_payload = {
                "temperature": round(temp, 1),
                "power": power_state_str
            }
            
            if power_data:
                print(f"⚡ 電壓: {power_data['voltage']}V, 功率: {power_data['power']}W")
                if power_data['power'] > 500.0:  # 假設超過 500W 算耗電 (可調整)
                    power_state_str = "waste"
                    update_payload["power"] = power_state_str # 更新狀態
                
                # 👇 新增：把詳細的電量數據打包成一個物件，放進 energy 欄位
                update_payload["energy"] = {
                    "voltage": power_data['voltage'],   # 電壓 (V)
                    "current": power_data['current'],   # 電流 (A)
                    "watt": power_data['power'],        # 實時功率 (W)
                    "total_wh": power_data['energy']    # 累積消耗電量 (Wh)
                }
            else:
                # 👇 補上這行，才不會無聲無息地失敗
                print("⚠️ PZEM 讀取失敗：腳位錯誤或 110V 未通電！")
                
#             # --- 讀取專業版 PZEM 數據 ---
#             power_state_str = "safe" 
#             
#             try:
#                 # 專業版通常是用特定的 get() 函式來獲取數值
#                 volts = power_meter.get_voltage()
#                 watts = power_meter.get_active_power()
#                 
#                 print(f"⚡ 電壓: {volts}V, 功率: {watts}W")
#                 if watts > 500.0:
#                     power_state_str = "waste"
#             except Exception as e:
#                 print("PZEM 專業版讀取失敗:", e)
                      
            firebase_zone_url = f"https://smart-timer-app-7da95-default-rtdb.firebaseio.com/users/{MY_UID}/zones/{MY_ZONE_ID}.json"
            
            try:
                res = urequests.patch(firebase_zone_url, json=update_payload)
                print(f"🔥 Firebase 回傳狀態碼: {res.status_code}")
                print(f"🔥 Firebase 回傳內容: {res.text}")
                if res.status_code == 200:
                    print(f"✅ 溫度 {temp:.1f}°C 與電表數據已真正同步！")
                else:
                    print("⚠️ 警告：Firebase 拒絕了你的資料更新！")
                res.close()
            except Exception as e:
                print("溫度與耗電更新失敗:", e)  
        # 重置計時器，等待下一次回報
        last_temp_report = current_time
    
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