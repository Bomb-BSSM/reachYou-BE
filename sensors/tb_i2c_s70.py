import smbus2

class TBI2CS70:
    def __init__(self, bus_number=1, address=0x3A):
        self.bus = smbus2.SMBus(bus_number)
        self.address = address
        
    def read_object_temp(self):
        try:
            data = self.bus.read_word_data(self.address, 0x07)
            temp = (data * 0.02) - 273.15
            return round(temp, 1)
        except Exception as e:
            print(f"온도 읽기 오류: {e}")
            return None
    
    def close(self):
        self.bus.close()