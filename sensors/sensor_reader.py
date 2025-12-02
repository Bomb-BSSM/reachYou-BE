import time
from sensors.tb_i2c_s70 import TBI2CS70
from sensors.heart_sensor import HeartRateSensor

class SensorManager:
    def __init__(self, temp_address=0x3A, heart_channel=1):
        print("\n센서 초기화 중...")
        
        try:
            self.temp_sensor = TBI2CS70(address=temp_address)
        except Exception as e:
            print(f"온도센서 초기화 실패: {e}")
            self.temp_sensor = None
        
        try:
            self.heart_sensor = HeartRateSensor(channel=heart_channel)
        except Exception as e:
            print(f"심박센서 초기화 실패: {e}")
            self.heart_sensor = None
        
        print("센서 초기화 완료!\n")
    
    def read_temperature(self, samples=5):
        if not self.temp_sensor:
            return None
        
        temps = []
        for _ in range(samples):
            temp = self.temp_sensor.read_object_temp()
            if temp is not None:
                temps.append(temp)
            time.sleep(0.2)
        
        if temps:
            avg_temp = sum(temps) / len(temps)
            return round(avg_temp, 1)
        return None
    
    def read_heart_rate(self, duration=15):
        if not self.heart_sensor:
            return None
        return self.heart_sensor.detect_heartbeat(duration=duration)
    
    def read_sensors(self):
        print("센서 데이터 수집 중...")
        
        temperature = self.read_temperature(samples=5)
        heart_rate = self.read_heart_rate(duration=15)
        
        return {
            'temperature': temperature if temperature else 36.5,
            'heart_rate': heart_rate if heart_rate else 70
        }
    
    def close(self):
        if self.temp_sensor:
            self.temp_sensor.close()
        if self.heart_sensor:
            self.heart_sensor.close()