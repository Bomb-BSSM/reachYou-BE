import spidev
import time

class HeartRateSensor:
    def __init__(self, channel=0):
        self.channel = channel
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
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
        """
        심박수 측정
        
        Args:
            duration: 측정 시간 (초)
        
        Returns:
            심박수 (BPM) 또는 None
        """
        print(f"\n{duration}초 동안 심박수 측정 중...")
        print("손가락을 센서에 가볍게 올려놓으세요.")
        print("너무 세게 누르지 마세요!\n")
        
        samples = []
        start_time = time.time()
        
        # 데이터 수집
        print("데이터 수집 중...")
        while time.time() - start_time < duration:
            value = self.read_adc()
            samples.append(value)
            
            # 진행 상황 표시
            elapsed = time.time() - start_time
            progress = int((elapsed / duration) * 20)
            bar = "█" * progress + "░" * (20 - progress)
            print(f"\r[{bar}] {elapsed:.1f}/{duration}초 | 현재값: {value:4d}", end="", flush=True)
            
            time.sleep(0.01)  # 100Hz 샘플링
        
        print("\n\n분석 중...")
        
        # 임계값 자동 설정
        mean_value = self.calculate_mean(samples)
        std_value = self.calculate_std(samples)
        threshold = mean_value + (std_value * 0.5)
        
        print(f"평균값: {mean_value:.1f}")
        print(f"표준편차: {std_value:.1f}")
        print(f"임계값: {threshold:.1f}")
        
        # 신호 품질 확인
        signal_range = max(samples) - min(samples)
        print(f"신호 변화폭: {signal_range}")
        
        if signal_range < 50:
            print("\n⚠️  신호가 약합니다!")
            print("- 손가락을 센서에 더 밀착시켜보세요")
            print("- LED가 손가락을 통과하는지 확인하세요")
            return None
        
        # 심박 감지
        beats = 0
        last_beat_time = 0
        beat_intervals = []
        
        print("\n심박 감지 중...")
        for i, value in enumerate(samples):
            current_time = i * 0.01
            
            # 심박 감지 (상승 에지)
            if i > 0 and samples[i-1] < threshold and value >= threshold:
                # 최소 간격 확인 (0.3초 = 200 BPM 이상 방지)
                if current_time - last_beat_time > 0.3:
                    beats += 1
                    if last_beat_time > 0:
                        interval = current_time - last_beat_time
                        beat_intervals.append(interval)
                        print(f"  💓 심박 #{beats} 감지 (간격: {interval:.2f}초)")
                    last_beat_time = current_time
        
        print(f"\n총 {beats}회 심박 감지")
        
        # 결과 계산
        if beats > 1 and beat_intervals:
            avg_interval = self.calculate_mean(beat_intervals)
            avg_bpm = 60 / avg_interval if avg_interval > 0 else 0
            
            print(f"\n{'='*50}")
            print(f"✓ 측정 완료!")
            print(f"{'='*50}")
            print(f"감지된 심박: {beats}회")
            print(f"평균 심박 간격: {avg_interval:.2f}초")
            print(f"심박수: {int(avg_bpm)} BPM")
            print(f"{'='*50}")
            
            # 정상 범위 확인
            if 50 <= avg_bpm <= 100:
                print("상태: ✅ 정상 범위")
            elif avg_bpm < 50:
                print("상태: ⚠️  느림 (서맥 의심)")
            else:
                print("상태: ⚠️  빠름 (빈맥 의심)")
            
            return int(avg_bpm)
        else:
            print("\n❌ 심박을 충분히 감지하지 못했습니다")
            print("다시 시도해주세요:")
            print("- 손가락을 센서에 가볍게 올려놓기")
            print("- 측정 중 움직이지 않기")
            print("- 센서 LED가 손가락을 통과하는지 확인")
            return None
    
    def close(self):
        self.spi.close()


def main():
    print("="*60)
    print("심박수 측정 테스트")
    print("="*60)
    
    sensor = HeartRateSensor(channel=0)
    
    try:
        # 1. 신호 확인 (5초)
        print("\n1단계: 신호 품질 확인 (5초)")
        input("준비되면 Enter를 누르세요...")
        
        print("\n신호 테스트 중...")
        test_values = []
        start = time.time()
        while time.time() - start < 5:
            value = sensor.read_adc()
            test_values.append(value)
            bar = "█" * int(value / 15)
            print(f"\r{value:4d} | {bar}     ", end="", flush=True)
            time.sleep(0.05)
        
        print(f"\n\n신호 범위: {min(test_values)} ~ {max(test_values)}")
        print(f"변화폭: {max(test_values) - min(test_values)}")
        
        if max(test_values) - min(test_values) < 50:
            print("\n⚠️  신호가 약합니다!")
            print("센서에 손가락을 더 밀착시켜보세요")
            return
        
        # 2. 심박수 측정
        print("\n\n2단계: 심박수 측정")
        input("손가락을 센서에 올리고 Enter를 누르세요...")
        
        bpm = sensor.detect_heartbeat(duration=15)
        
        if bpm:
            print(f"\n✓ 최종 심박수: {bpm} BPM")
        else:
            print("\n측정 실패. 다시 시도해주세요.")
    
    except KeyboardInterrupt:
        print("\n\n측정 중단")
    
    finally:
        sensor.close()
        print("센서 연결 종료")


if __name__ == "__main__":
    main()