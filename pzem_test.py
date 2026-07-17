from machine import UART, Pin
import time
import struct

class PZEM:
    def __init__(self, uart_id=1, tx_pin=9, rx_pin=8):
        # 依照你的電路圖，ESP32 TX = D10, RX = D9
        self.uart = UART(uart_id, baudrate=9600, tx=Pin(tx_pin), rx=Pin(rx_pin), timeout=100)

    def read_data(self):
        # 發送 Modbus RTU 讀取指令 (讀取電壓、電流、功率等 10 個暫存器)
        req = b'\x01\x04\x00\x00\x00\x0A\x70\x0D'
        self.uart.write(req)
        time.sleep(0.1) # 等待 PZEM 處理並回傳

        if self.uart.any():
            resp = self.uart.read()
            # 檢查回傳長度是否為標準的 25 bytes
            if resp and len(resp) == 25:
                try:
                    # 解析二進位資料
                    voltage = struct.unpack('>H', resp[3:5])[0] / 10.0
                    # 2. 電流解析 (32-bit，修正高低字組對調 Word Swap)
                    # 先解出兩個 16-bit 的值 (curr_low, curr_high)
                    curr_low, curr_high = struct.unpack('>HH', resp[5:9])
                    # 將高位字組左移 16 位元，再與低位字組結合
                    current = ((curr_high << 16) | curr_low) / 1000.0
                    current = ((curr_high << 16) | curr_low) / 1000.0
                    # 3. 功率解析 (32-bit，修正高低字組對調 Word Swap)
                    pow_low, pow_high = struct.unpack('>HH', resp[9:13])
                    power = ((pow_high << 16) | pow_low) / 10.0
                    # 4. 累積電量解析 (32-bit，修正高低字組對調 Word Swap)
                    eng_low, eng_high = struct.unpack('>HH', resp[13:17])
                    energy = (eng_high << 16) | eng_low
                    frequency = struct.unpack('>H', resp[17:19])[0] / 10.0
                    pf = struct.unpack('>H', resp[19:21])[0] / 100.0

                    return {
                        "voltage": voltage,     # 電壓 (V)
                        "current": current,     # 電流 (A)
                        "power": power,         # 當前功率 (W)
                        "energy": energy,       # 累積消耗電量 (Wh)
                        "frequency": frequency, # 頻率 (Hz)
                        "pf": pf                # 功率因數
                    }
                except Exception as e:
                    print("PZEM 資料解析錯誤:", e)
        return None

# ==========================================
# 👇 以下為直接執行此檔案時的專屬測試程式碼 👇
# ==========================================
if __name__ == '__main__':
    print("--- PZEM-004T 實機測試開始 ---")

    # 初始化電量計 (因為現在就在同一個檔案裡，直接呼叫 PZEM 即可)
    power_meter = PZEM(uart_id=1, tx_pin=9, rx_pin=8)

    while True:
        power_data = power_meter.read_data()
        
        if power_data:
            print("==============================")
            print(f"⚡ 電壓 (Voltage)  : {power_data['voltage']} V")
            print(f"🔌 電流 (Current)  : {power_data['current']} A")
            print(f"🔥 功率 (Power)    : {power_data['power']} W")
            print(f"🔋 累積電量(Energy): {power_data['energy']} Wh")
            print(f"⏱️ 頻率 (Frequency): {power_data['frequency']} Hz")
            print(f"📈 功率因數 (PF)   : {power_data['pf']}")
        else:
            print("⚠️ 讀取失敗：請檢查 TX/RX 腳位、分壓電阻，以及 110V 是否確實供電！")
            
        time.sleep(2) # 每 2 秒讀取一次