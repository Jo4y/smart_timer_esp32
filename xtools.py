# xtools.py    
from machine import Pin
import urandom, math
import time, network, urequests
import ubinascii
import machine
#import config
import ujson, socket

# Wi-Fi 配網與連線模組
CONFIG_FILE = 'wifi_config.json'

def load_wifi_config():
    """從 Flash 讀取儲存的 Wi-Fi 帳密"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return ujson.load(f)
    except:
        return None

def save_wifi_config(ssid, password):
    """將 Wi-Fi 帳密存入 Flash"""
    with open(CONFIG_FILE, 'w') as f:
        ujson.dump({"ssid": ssid, "password": password}, f)

def start_ap_and_listen():
    """AP 模式，並開啟微型伺服器等待 App 傳送密碼"""
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Smart_Timer_Setup", channel= 1, authmode=network.AUTH_OPEN) # 開放網路
    
    ip = ap.ifconfig()[0]
    print(f"📡 AP 模式啟動！請將手機連上 Wi-Fi: Smart_Timer_Setup")
    print(f"🌐 伺服器監聽 IP: {ip}")

    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 80))
    s.listen(1)

    print("👂 等待 App 傳送設定檔...")
    
    # (LED保持恆亮)表示處於 AP 模式等待中
    wifi_led = Pin(2, Pin.OUT, value=1) 
    
    while True:
        conn, addr = s.accept()
        print('收到連線來自:', addr)
        try:
            request = conn.recv(1024).decode('utf-8')
            
            if 'POST' in request:
                body = request.split('\r\n\r\n')[1]
                data = ujson.loads(body)
                
                new_ssid = data.get('ssid')
                new_pwd = data.get('password')

                if new_ssid and new_pwd:
                    print(f"✅ 收到新 Wi-Fi 設定！SSID: {new_ssid}")
                    save_wifi_config(new_ssid, new_pwd)
                    
                    response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}"
                    conn.send(response.encode())
                    conn.close()
                    
                    print("🔄 準備重啟以套用新設定...")
                    # 快速閃爍三次表收到密碼並準備重啟
                    for _ in range(3):
                        wifi_led.value(0)
                        time.sleep(0.1)
                        wifi_led.value(1)
                        time.sleep(0.1)
                    machine.reset() 
            else:
                response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<h1>Smart Timer is Waiting for App...</h1>"
                conn.send(response.encode())
                
        except Exception as e:
            print("處理請求時發生錯誤:", e)
        finally:
            conn.close()

def auto_connect(timeout=15):
    """主邏輯：先嘗試 STA (含 LED 閃爍邏輯)，失敗就退回 AP"""
    wifi_led = Pin(2, Pin.OUT, value=1)
    config = load_wifi_config()
    sta = network.WLAN(network.STA_IF)
    
    sta.active(False)
    time.sleep(0.5)
    sta.active(True)

    if config:
        ssid = config['ssid']
        pwd = config['password']
        print(f"🔍 找到紀錄，嘗試連線至: {ssid}")
        sta.connect(ssid, pwd)
        
        start_time = time.time()
        while not sta.isconnected():
            wifi_led.value(0)
            time.sleep_ms(300)
            wifi_led.value(1)
            time.sleep_ms(300)
            if time.time() - start_time > timeout:
                print("❌ Wifi connecting timeout!")
                break
                
        if sta.isconnected():
            wifi_led.value(0) # 連線成功，熄滅 LED
            print("✅ network config:", sta.ifconfig())
            return sta.ifconfig()[0] 
    else:
        print("⚠️ 找不到 Wi-Fi 紀錄！")

    # 如果沒紀錄，或連線超時，進入 AP 模式
    start_ap_and_listen()

def get_id():
    return ubinascii.hexlify(machine.unique_id())

def get_num(x):
    return float("".join(ele for ele in x if ele.isdigit() or ele =="."))

def random_in_range(low=0, high=1000):
    r1 = urandom.getrandbits(32)
    r2 = r1 % (high-low) + low
    return math.floor(r2)

def map_range(x, in_min, in_max, out_min, out_max):
   return int((x-in_min) * (out_max-out_min) / (in_max-in_min) + out_min)


# def connect_wifi_led(ssid=config.SSID, passwd=config.PASSWORD, timeout=15):
#     wifi_led=Pin(2, Pin.OUT, value=1)
#     sta = network.WLAN(network.STA_IF)
#     sta.active(True)
#     start_time=time.time() # 記錄時間判斷是否超時
#     if not sta.isconnected():
#         print("Connecting to network...")
#         sta.connect(ssid, passwd)
#         while not sta.isconnected():
#             wifi_led.value(0)
#             time.sleep_ms(300)
#             wifi_led.value(1)
#             time.sleep_ms(300)
#             # 判斷是否超過timeout秒數
#             if time.time()-start_time > timeout:
#                 print("Wifi connecting timeout!")
#                 break
#     if sta.isconnected():
#         wifi_led.value(0)
#         print("network config:", sta.ifconfig())
#         return sta.ifconfig()[0]
    

def show_error(final_state=0):
    led = Pin(2, Pin.OUT)   # Built-in D4
    for i in range(3):
        led.value(1)
        time.sleep(0.5)
        led.value(0)
        time.sleep(0.5)
    led.value(final_state)    

def webhook_post(url, value):
    print("invoking webhook")
    from xrequests import post
    r = post(url, data=value)
    if r is not None and r.status_code == 200:
        print("Webhook invoked")
    else:
        print("Webhook failed")
        show_error()

def webhook_get(url):
    print("invoking webhook")
    r = urequests.get(url)
    if r is not None and r.status_code == 200:
        print("Webhook invoked")
    else:
        print("Webhook failed")
        show_error()
        
def line_msg(token, message):
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/x-www-form-urlencoded"
    } 
    params = {"message": message}
    from xrequests import post
    r = post("https://notify-api.line.me/api/notify",
                    params=params, headers=headers)  
    if r is not None and r.status_code == 200:
        print("Message sent...")
    else:
        print("Error! Failed to send notification message...")  
     
def pad_zero(v):
    if v < 10:
        return '0' + str(v)
    else:
        return str(v)
     
def format_datetime(local_time):
    Y,M,D,H,m,S,W,ds = local_time
    t = str(Y) + '-'
    t += pad_zero(M)
    t += '-'
    t += pad_zero(D)
    t += ' '
    t += pad_zero(H)
    t += ':'
    t += pad_zero(m)
    t += ':'
    t += pad_zero(S)
    return t