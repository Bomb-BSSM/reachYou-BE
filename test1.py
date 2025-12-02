import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000

channel = 0

print(f"CH{channel} 실시간 모니터링")
print("손가락을 센서에 올려보세요")
print("=" * 60)

try:
    values = []
    for i in range(100):
        adc = spi.xfer2([1, (8 + channel) << 4, 0])
        data = ((adc[1] & 3) << 8) + adc[2]
        values.append(data)
        bar = "█" * int(data / 20)
        print(f"\r{data:4d} | {bar}          ", end="", flush=True)
        time.sleep(0.05)
    
    print(f"\n\n최소값: {min(values)}")
    print(f"최대값: {max(values)}")
    print(f"평균값: {sum(values)/len(values):.1f}")
    print(f"변화폭: {max(values) - min(values)}")
    
    if max(values) - min(values) < 10:
        print("\n신호 변화가 거의 없습니다!")
        print("- 센서가 올바른 채널에 연결되었는지 확인")
        print("- 센서 전원(+, -)이 제대로 연결되었는지 확인")
        print("- 센서가 작동하는지 확인 (LED 있으면 켜져있어야 함)")
    
except KeyboardInterrupt:
    print("\n\n테스트 종료")
finally:
    spi.close()