import smbus2
import time

class TBI2CS70:
    def __init__(self, bus_number=1, address=0x3A):
        self.bus = smbus2.SMBus(bus_number)
        self.address = address
        
    def read_ambient_temp(self):
        try:
            data = self.bus.read_word_data(self.address, 0x06)
            temp = (data * 0.02) - 273.15
            return round(temp, 2)
        except Exception as e:
            print(f"주변 온도 읽기 오류: {e}")
            return None
    
    def read_object_temp(self):
        try:
            data = self.bus.read_word_data(self.address, 0x07)
            temp = (data * 0.02) - 273.15
            return round(temp, 2)
        except Exception as e:
            print(f"물체 온도 읽기 오류: {e}")
            return None
    
    def close(self):
        """연결 종료"""
        self.bus.close()

def test_sensor():
    print("TB-I2C-S70 센서 테스트 시작...\n")
    
    sensor = TBI2CS70(address=0x3A)
    
    try:
        for i in range(10):
            ambient = sensor.read_ambient_temp()
            object_temp = sensor.read_object_temp()
            
            print(f"측정 {i+1}:")
            print(f"  주변 온도: {ambient}°C")
            print(f"  물체 온도: {object_temp}°C")
            print()
            
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n테스트 중단")
    
    finally:
        sensor.close()
        print("센서 연결 종료")

if __name__ == "__main__":
    test_sensor()