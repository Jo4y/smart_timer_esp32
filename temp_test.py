import machine
import onewire
import ds18x20
import time

# 1. 設定腳位 (請改成你實際接 DATA 的 GPIO 腳位，這裡是 GPIO 5)
data_pin = machine.Pin(4)

# 2. 建立 1-Wire 與 DS18B20 物件
ow = onewire.OneWire(data_pin)
ds = ds18x20.DS18X20(ow)

# 3. 掃描這條線上所有的 DS18B20 設備
print("正在尋找溫度感測器...")
roms = ds.scan()
print('找到設備清單:', roms)

if not roms:
    print("❌ 找不到任何 DS18B20 設備！請檢查線路是否接錯，以及是否有加上 4.7kΩ 電阻！")
else:
    print("✅ 成功找到設備，開始測溫！\n")
    
    # 4. 迴圈讀取溫度
    while True:
        try:
            # 命令所有設備開始轉換溫度
            ds.convert_temp()
            
            # ⚠️ 經典重點：DS18B20 轉換溫度需要時間，最少必須等待 750 毫秒
            time.sleep_ms(750)
            
            # 依序讀取每一個找到的設備溫度 (雖然你通常只會接一個)
            for rom in roms:
                temp = ds.read_temp(rom)
                print(f"🌡️ 目前溫度: {temp:.2f} °C")
                
            time.sleep(2) # 休息 2 秒再測下一次
            
        except Exception as e:
            print("讀取失敗:", e)
            time.sleep(2)