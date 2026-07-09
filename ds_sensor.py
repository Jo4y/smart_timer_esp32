import machine
import onewire
import ds18x20
import time

_ds = None
_roms = []

def init_sensor(pin_num=2):
    """初始化感測器並回傳是否成功找到設備"""
    global _ds, _roms
    try:
        ow = onewire.OneWire(machine.Pin(pin_num))
        _ds = ds18x20.DS18X20(ow)
        _roms = _ds.scan()
        return len(_roms) > 0
    except:
        return False

def get_temp():
    """讀取並回傳溫度浮點數，如果失敗則回傳 None"""
    if not _ds or not _roms:
        return None
    try:
        _ds.convert_temp()
        time.sleep_ms(750) # 必須的轉換時間
        return _ds.read_temp(_roms[0])
    except:
        return None