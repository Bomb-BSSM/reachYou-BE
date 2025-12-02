import spidev
import time

class HeartRateSensor:
    def __init__(self, channel=1, spi_bus=0, spi_device=0):
        self.channel = channel
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = 1350000
        
    def read_adc(self):
        adc = self.spi.xfer2([1, (8 + self.channel) << 4, 0])
        data = ((adc[1] & 3) << 8) + adc[2]
        return data
    
    def calculate_mean(self, values):
        return sum(values) / len(values) if values else 0
    
    def calculate_std(self, values):
        if not values:
            return 0
        mean = self.calculate_mean(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def detect_heartbeat(self, duration=15):
        samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            value = self.read_adc()
            samples.append(value)
            time.sleep(0.01)
        
        mean_value = self.calculate_mean(samples)
        std_value = self.calculate_std(samples)
        threshold = mean_value + (std_value * 0.5)
        
        beats = 0
        last_beat_time = 0
        beat_intervals = []
        
        for i, value in enumerate(samples):
            current_time = i * 0.01
            
            if i > 0 and samples[i-1] < threshold and value >= threshold:
                if current_time - last_beat_time > 0.3:
                    beats += 1
                    if last_beat_time > 0:
                        interval = current_time - last_beat_time
                        beat_intervals.append(interval)
                    last_beat_time = current_time
        
        if beats > 1 and beat_intervals:
            avg_interval = self.calculate_mean(beat_intervals)
            avg_bpm = 60 / avg_interval if avg_interval > 0 else 0
            return int(avg_bpm)
        return None
    
    def close(self):
        self.spi.close()