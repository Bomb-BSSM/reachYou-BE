import spidev
import time
from collections import deque

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
    
    def moving_average(self, data, window=5):
        """이동 평균으로 노이즈 제거"""
        if len(data) < window:
            return data
        
        smoothed = []
        for i in range(len(data)):
            if i < window:
                smoothed.append(sum(data[:i+1]) / (i+1))
            else:
                smoothed.append(sum(data[i-window+1:i+1]) / window)
        return smoothed
    
    def find_peaks(self, data, min_distance=30, min_height_ratio=0.6):
        """
        피크(봉우리) 찾기 - 실제 심박만 감지
        
        Args:
            data: 신호 데이터
            min_distance: 최소 피크 간격 (샘플 수) - 30 = 0.3초 = 200 BPM
            min_height_ratio: 최소 피크 높이 비율 (신호 범위의 60%)
        """
        if len(data) < 3:
            return []
        
        # 신호 범위 계산
        signal_min = min(data)
        signal_max = max(data)
        signal_range = signal_max - signal_min
        
        # 동적 임계값 (신호 최소값 + 범위의 60%)
        threshold = signal_min + (signal_range * min_height_ratio)
        
        peaks = []
        last_peak_idx = -min_distance
        
        for i in range(1, len(data) - 1):
            # 현재 값이 양옆보다 크고, 임계값 이상이며, 최소 간격 유지
            if (data[i] > data[i-1] and 
                data[i] > data[i+1] and 
                data[i] > threshold and
                i - last_peak_idx >= min_distance):
                
                peaks.append(i)
                last_peak_idx = i
        
        return peaks
    
    def detect_heartbeat(self, duration=15):
        """
        개선된 심박수 측정
        
        Args:
            duration: 측정 시간 (초)
        
        Returns:
            심박수 (BPM) 또는 None
        """
        print(f"\n{'='*60}")
        print(f"{duration}초 동안 심박수 측정")
        print(f"{'='*60}")
        print("📌 측정 방법:")
        print("  1. 손가락을 센서에 가볍게 올려놓기")
        print("  2. 측정 중 절대 움직이지 않기")
        print("  3. 너무 세게 누르지 않기\n")
        
        input("준비되면 Enter를 누르세요...")
        print()
        
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
            print(f"\r[{bar}] {elapsed:.1f}/{duration}초 | 신호: {value:4d}", end="", flush=True)
            
            time.sleep(0.01)  # 100Hz 샘플링
        
        print("\n\n분석 중...\n")
        
        # 신호 품질 확인
        signal_min = min(samples)
        signal_max = max(samples)
        signal_range = signal_max - signal_min
        signal_mean = sum(samples) / len(samples)
        
        print(f"📊 신호 분석:")
        print(f"  - 최소값: {signal_min}")
        print(f"  - 최대값: {signal_max}")
        print(f"  - 평균값: {signal_mean:.1f}")
        print(f"  - 변화폭: {signal_range}")
        
        # 신호 품질 체크
        if signal_range < 100:
            print("\n❌ 신호가 너무 약합니다!")
            print("💡 해결 방법:")
            print("  - 손가락을 센서에 더 밀착시키기")
            print("  - LED가 손가락을 통과하는지 확인")
            print("  - 손가락의 다른 부분으로 시도")
            return None
        
        if signal_range > 700:
            print("\n⚠️  신호 변화가 너무 큽니다!")
            print("💡 해결 방법:")
            print("  - 손가락을 너무 세게 누르지 않기")
            print("  - 측정 중 움직이지 않기")
        
        # 이동 평균으로 노이즈 제거
        print("\n🔄 노이즈 제거 중...")
        smoothed_samples = self.moving_average(samples, window=10)
        
        # 피크 찾기 (실제 심박)
        print("💓 심박 감지 중...")
        peaks = self.find_peaks(
            smoothed_samples, 
            min_distance=30,  # 0.3초 = 200 BPM 이상 방지
            min_height_ratio=0.6  # 신호 범위의 60% 이상만 심박으로 인식
        )
        
        print(f"\n감지된 심박: {len(peaks)}회")
        
        # 심박 간격 계산
        if len(peaks) >= 2:
            intervals = []
            for i in range(1, len(peaks)):
                interval = (peaks[i] - peaks[i-1]) * 0.01  # 샘플 → 초
                intervals.append(interval)
                print(f"  💓 심박 #{i}: {interval:.2f}초 간격")
            
            # 이상치 제거 (평균에서 너무 벗어난 값 제거)
            if len(intervals) >= 3:
                mean_interval = sum(intervals) / len(intervals)
                std_interval = (sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5
                
                # 평균 ± 1.5 표준편차 범위 내의 값만 사용
                valid_intervals = [x for x in intervals if abs(x - mean_interval) < 1.5 * std_interval]
                
                if len(valid_intervals) >= 2:
                    intervals = valid_intervals
                    print(f"\n✂️  이상치 제거: {len(valid_intervals)}/{len(intervals)}개 간격 사용")
            
            # 최종 심박수 계산
            avg_interval = sum(intervals) / len(intervals)
            avg_bpm = 60 / avg_interval if avg_interval > 0 else 0
            
            # 추가 검증: 정상 범위 확인
            if 40 <= avg_bpm <= 180:
                print(f"\n{'='*60}")
                print(f"✅ 측정 완료!")
                print(f"{'='*60}")
                print(f"평균 심박 간격: {avg_interval:.2f}초")
                print(f"심박수: {int(avg_bpm)} BPM")
                print(f"{'='*60}")
                
                # 상태 표시
                if 50 <= avg_bpm <= 100:
                    print("상태: ✅ 정상 범위 (안정시 심박수)")
                elif 40 <= avg_bpm < 50:
                    print("상태: 💙 느림 (운동선수나 안정 시 정상)")
                elif 100 < avg_bpm <= 120:
                    print("상태: 💛 약간 빠름 (긴장 또는 가벼운 활동)")
                else:
                    print("상태: 🧡 빠름 (운동 또는 흥분 상태)")
                
                return int(avg_bpm)
            else:
                print(f"\n⚠️  측정값({int(avg_bpm)} BPM)이 정상 범위를 벗어났습니다")
                print("다시 측정해주세요:")
                print("  - 손가락을 센서에 올린 채로 움직이지 않기")
                print("  - 너무 세게 누르지 않기")
                print("  - 긴장을 풀고 편안한 상태 유지")
                return None
        else:
            print("\n❌ 심박을 충분히 감지하지 못했습니다")
            print("💡 해결 방법:")
            print("  - 측정 시간을 20초로 늘려보기")
            print("  - 손가락을 센서에 가볍게 올리고 움직이지 않기")
            print("  - 다른 손가락으로 시도해보기")
            return None
    
    def test_signal(self, duration=5):
        """신호 테스트"""
        print(f"\n{'='*60}")
        print(f"신호 품질 테스트 ({duration}초)")
        print(f"{'='*60}\n")
        
        values = []
        start = time.time()
        
        while time.time() - start < duration:
            value = self.read_adc()
            values.append(value)
            
            # 실시간 그래프
            bar_length = int(value / 10)
            bar = "█" * min(bar_length, 80)
            print(f"\r{value:4d} | {bar}     ", end="", flush=True)
            time.sleep(0.05)
        
        print(f"\n\n{'='*60}")
        print("신호 분석 결과:")
        print(f"{'='*60}")
        print(f"최소값: {min(values)}")
        print(f"최대값: {max(values)}")
        print(f"평균값: {sum(values)/len(values):.1f}")
        print(f"변화폭: {max(values) - min(values)}")
        
        signal_range = max(values) - min(values)
        
        if signal_range < 100:
            print("\n❌ 신호가 약합니다!")
            print("💡 손가락을 센서에 더 밀착시켜보세요")
        elif signal_range > 700:
            print("\n⚠️  신호 변화가 너무 큽니다!")
            print("💡 손가락을 너무 세게 누르지 마세요")
        else:
            print("\n✅ 신호 품질이 좋습니다!")
            print("💡 심박수 측정을 시작할 수 있습니다")
    
    def close(self):
        self.spi.close()


def main():
    print("="*60)
    print("개선된 심박수 측정 시스템")
    print("="*60)
    
    sensor = HeartRateSensor(channel=0)
    
    try:
        while True:
            print("\n\n메뉴:")
            print("1. 신호 테스트 (5초)")
            print("2. 심박수 측정 (15초)")
            print("3. 심박수 측정 (20초 - 더 정확함)")
            print("4. 종료")
            
            choice = input("\n선택 (1-4): ").strip()
            
            if choice == "1":
                sensor.test_signal(duration=5)
            
            elif choice == "2":
                bpm = sensor.detect_heartbeat(duration=15)
                if bpm:
                    print(f"\n✅ 최종 결과: {bpm} BPM")
            
            elif choice == "3":
                bpm = sensor.detect_heartbeat(duration=20)
                if bpm:
                    print(f"\n✅ 최종 결과: {bpm} BPM")
            
            elif choice == "4":
                print("\n프로그램 종료")
                break
            
            else:
                print("잘못된 선택입니다")
    
    except KeyboardInterrupt:
        print("\n\n프로그램 중단")
    
    finally:
        sensor.close()
        print("센서 연결 종료")


if __name__ == "__main__":
    main()