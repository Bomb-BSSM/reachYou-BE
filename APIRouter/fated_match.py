from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
import sys
import os
import asyncio
import json
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sensors.sensor_reader import SensorManager
# compatibility 모듈에서 궁합 계산 함수 import
from .compatibility import calculate_total_compatibility

router = APIRouter(prefix="/api/fated-match", tags=["fated_match"])

class SensorData(BaseModel):
    user_id: int
    heart_rate: int
    temperature: float

def get_db():
    from config import engine
    connection = engine.raw_connection()
    try:
        yield connection
    finally:
        connection.close()


@router.post("/update-sensor")
def update_sensor_data(data: SensorData, connection = Depends(get_db)):
    """센서 데이터 업데이트 (심박수, 온도)"""
    try:
        cursor = connection.cursor()
        
        update_query = """
            UPDATE users 
            SET heart_rate = %s, temperature = %s, last_measured_at = NOW()
            WHERE user_id = %s
        """
        cursor.execute(update_query, (
            data.heart_rate,
            data.temperature,
            data.user_id
        ))
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": "센서 데이터가 업데이트되었습니다",
            "data": {
                "user_id": data.user_id,
                "heart_rate": data.heart_rate,
                "temperature": data.temperature
            }
        }
        
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/{user_id}")
def get_fated_matches(user_id: int, limit: int = 2, connection = Depends(get_db)):
    """
    특정 사용자의 운명의 상대 조회
    
    Args:
        user_id: 사용자 ID
        limit: 반환할 인원 (기본 2명)
    """
    try:
        cursor = connection.cursor()
        
        # 현재 사용자 정보
        user_query = """
            SELECT user_id, username, mbti, profile_image_url, heart_rate, temperature
            FROM users
            WHERE user_id = %s
        """
        cursor.execute(user_query, (user_id,))
        current_user = cursor.fetchone()
        
        if not current_user:
            cursor.close()
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        current_username = current_user[1]
        current_mbti = current_user[2]
        current_image = current_user[3]
        current_heart_rate = current_user[4] or 70
        current_temperature = current_user[5] or 36.5
        
        # 다른 모든 사용자
        candidates_query = """
            SELECT user_id, username, mbti, profile_image_url, heart_rate, temperature
            FROM users
            WHERE user_id != %s
        """
        cursor.execute(candidates_query, (user_id,))
        all_candidates = cursor.fetchall()
        
        if len(all_candidates) < 1:
            cursor.close()
            raise HTTPException(status_code=400, detail="다른 사용자가 없습니다")
        
        # 궁합 계산
        candidates_with_scores = []
        
        for candidate in all_candidates:
            candidate_id = candidate[0]
            candidate_name = candidate[1]
            candidate_mbti = candidate[2]
            candidate_image = candidate[3]
            candidate_heart_rate = candidate[4] or 70
            candidate_temperature = candidate[5] or 36.5
            
            compatibility = calculate_total_compatibility(
                current_mbti, candidate_mbti,
                current_heart_rate, candidate_heart_rate,
                current_temperature, candidate_temperature
            )
            
            candidates_with_scores.append({
                "user_id": candidate_id,
                "username": candidate_name,
                "mbti": candidate_mbti,
                "profile_image_url": candidate_image,
                "compatibility_score": compatibility["total_score"],
                "mbti_score": compatibility["mbti_score"],
                "heart_rate_score": compatibility["heart_rate_score"],
                "temperature_score": compatibility["temperature_score"]
            })
        
        # 점수 순 정렬
        candidates_with_scores.sort(key=lambda x: x["compatibility_score"], reverse=True)
        
        # 상위 N명 선택
        top_matches = candidates_with_scores[:limit]
        
        # DB에 저장
        cursor.execute("DELETE FROM fated_matches WHERE user_id = %s", (user_id,))
        
        for match in top_matches:
            insert_query = """
                INSERT INTO fated_matches (user_id, matched_user_id, match_score)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (
                user_id,
                match["user_id"],
                match["compatibility_score"]
            ))
        
        connection.commit()
        cursor.close()
        
        return {
            "user_id": user_id,
            "current_user": {
                "username": current_username,
                "mbti": current_mbti,
                "profile_image_url": current_image,
                "heart_rate": current_heart_rate,
                "temperature": current_temperature
            },
            "match_count": len(top_matches),
            "fated_matches": top_matches
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("/calculate/{user_id}")
def calculate_single_user_matches(user_id: int, connection = Depends(get_db)):
    """특정 사용자의 운명의 상대만 다시 계산 (추천!)"""
    try:
        cursor = connection.cursor()
        
        # 해당 사용자 정보 조회
        cursor.execute("""
            SELECT user_id, mbti, heart_rate, temperature
            FROM users
            WHERE user_id = %s
        """, (user_id,))
        current_user = cursor.fetchone()
        
        if not current_user:
            cursor.close()
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        user_mbti = current_user[1]
        user_heart_rate = current_user[2] or 70
        user_temperature = current_user[3] or 36.5
        
        # 다른 모든 사용자 조회
        cursor.execute("""
            SELECT user_id, mbti, heart_rate, temperature
            FROM users
            WHERE user_id != %s
        """, (user_id,))
        other_users = cursor.fetchall()
        
        if len(other_users) < 1:
            cursor.close()
            raise HTTPException(status_code=400, detail="다른 사용자가 없습니다")
        
        # 궁합 계산
        candidates_with_scores = []
        for other_user in other_users:
            other_id = other_user[0]
            other_mbti = other_user[1]
            other_heart_rate = other_user[2] or 70
            other_temperature = other_user[3] or 36.5
            
            compatibility = calculate_total_compatibility(
                user_mbti, other_mbti,
                user_heart_rate, other_heart_rate,
                user_temperature, other_temperature
            )
            
            candidates_with_scores.append({
                "user_id": other_id,
                "score": compatibility["total_score"]
            })
        
        # 점수 순 정렬 및 상위 2명 선택
        candidates_with_scores.sort(key=lambda x: x["score"], reverse=True)
        top_matches = candidates_with_scores[:2]
        
        # 해당 사용자의 기존 매칭만 삭제
        cursor.execute("DELETE FROM fated_matches WHERE user_id = %s", (user_id,))
        
        # 새로운 매칭 저장
        for match in top_matches:
            cursor.execute("""
                INSERT INTO fated_matches (user_id, matched_user_id, match_score)
                VALUES (%s, %s, %s)
            """, (user_id, match["user_id"], match["score"]))
        
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": f"사용자 {user_id}의 운명의 상대가 다시 계산되었습니다",
            "user_id": user_id,
            "match_count": len(top_matches)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("/calculate-all")
def calculate_all_matches(only_recent: bool = True, minutes: int = 60, connection = Depends(get_db)):
    """
    운명의 상대 계산
    
    Args:
        only_recent: True면 최근 측정한 사용자만 계산 (기본값)
        minutes: 최근 N분 이내 측정한 사용자만 (기본값: 60분)
    """
    try:
        cursor = connection.cursor()
        
        if only_recent:
            # 최근 N분 이내 측정한 사용자만 조회
            cursor.execute("""
                SELECT user_id, mbti, heart_rate, temperature
                FROM users
                WHERE last_measured_at >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
                  AND heart_rate IS NOT NULL
                  AND temperature IS NOT NULL
            """, (minutes,))
            recent_users = cursor.fetchall()
            
            if len(recent_users) == 0:
                cursor.close()
                raise HTTPException(
                    status_code=400, 
                    detail=f"최근 {minutes}분 이내 측정한 사용자가 없습니다"
                )
            
            print(f"\n{'='*60}")
            print(f"최근 {minutes}분 이내 측정한 사용자: {len(recent_users)}명")
            print(f"{'='*60}")
            
            # 전체 사용자 조회 (매칭 대상)
            cursor.execute("""
                SELECT user_id, mbti, heart_rate, temperature
                FROM users
            """)
            all_users = cursor.fetchall()
            
            # 최근 측정한 사용자들만 매칭 재계산
            updated_count = 0
            for user in recent_users:
                user_id = user[0]
                user_mbti = user[1]
                user_heart_rate = user[2] or 70
                user_temperature = user[3] or 36.5
                
                print(f"사용자 {user_id} 매칭 계산 중...")
                
                candidates_with_scores = []
                
                for other_user in all_users:
                    other_id = other_user[0]
                    
                    if user_id == other_id:
                        continue
                    
                    other_mbti = other_user[1]
                    other_heart_rate = other_user[2] or 70
                    other_temperature = other_user[3] or 36.5
                    
                    compatibility = calculate_total_compatibility(
                        user_mbti, other_mbti,
                        user_heart_rate, other_heart_rate,
                        user_temperature, other_temperature
                    )
                    
                    candidates_with_scores.append({
                        "user_id": other_id,
                        "score": compatibility["total_score"]
                    })
                
                candidates_with_scores.sort(key=lambda x: x["score"], reverse=True)
                top_matches = candidates_with_scores[:2]
                
                # 해당 사용자의 기존 매칭만 삭제
                cursor.execute("DELETE FROM fated_matches WHERE user_id = %s", (user_id,))
                
                # 새 매칭 저장
                for match in top_matches:
                    cursor.execute("""
                        INSERT INTO fated_matches (user_id, matched_user_id, match_score)
                        VALUES (%s, %s, %s)
                    """, (user_id, match["user_id"], match["score"]))
                
                updated_count += 1
                print(f"✓ 사용자 {user_id} 완료")
            
            connection.commit()
            cursor.close()
            
            return {
                "success": True,
                "message": f"최근 {minutes}분 이내 측정한 {updated_count}명의 운명의 상대가 계산되었습니다",
                "updated_users": updated_count,
                "total_users": len(all_users)
            }
            
        else:
            # 기존 방식: 전체 재계산
            cursor.execute("DELETE FROM fated_matches")
            
            cursor.execute("""
                SELECT user_id, mbti, heart_rate, temperature
                FROM users
            """)
            all_users = cursor.fetchall()
        
        if len(all_users) < 2:
            cursor.close()
            raise HTTPException(status_code=400, detail="최소 2명 이상 필요합니다")
        
        for user in all_users:
            user_id = user[0]
            user_mbti = user[1]
            user_heart_rate = user[2] or 70
            user_temperature = user[3] or 36.5
            
            candidates_with_scores = []
            
            for other_user in all_users:
                other_id = other_user[0]
                
                if user_id == other_id:
                    continue
                
                other_mbti = other_user[1]
                other_heart_rate = other_user[2] or 70
                other_temperature = other_user[3] or 36.5
                
                compatibility = calculate_total_compatibility(
                    user_mbti, other_mbti,
                    user_heart_rate, other_heart_rate,
                    user_temperature, other_temperature
                )
                
                candidates_with_scores.append({
                    "user_id": other_id,
                    "score": compatibility["total_score"]
                })
            
            candidates_with_scores.sort(key=lambda x: x["score"], reverse=True)
            top_matches = candidates_with_scores[:2]
            
            for match in top_matches:
                cursor.execute("""
                    INSERT INTO fated_matches (user_id, matched_user_id, match_score)
                    VALUES (%s, %s, %s)
                """, (user_id, match["user_id"], match["score"]))
        
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": f"총 {len(all_users)}명의 운명의 상대가 계산되었습니다",
            "total_users": len(all_users)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.websocket("/ws/measure/{user_id}")
async def websocket_measure_sensor(websocket: WebSocket, user_id: int):
    """
    웹소켓으로 실시간 센서 측정
    
    실시간 전송 데이터:
    - status: 현재 상태 (준비중, 측정중, 완료, 오류)
    - progress: 진행률 (0-100)
    - current_value: 현재 센서 값
    - message: 상태 메시지
    - result: 최종 측정 결과
    """
    await websocket.accept()
    
    try:
        # DB 연결
        from config import engine
        connection = engine.raw_connection()
        cursor = connection.cursor()
        
        # 사용자 확인
        cursor.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            await websocket.send_json({
                "status": "error",
                "message": "사용자를 찾을 수 없습니다"
            })
            await websocket.close()
            return
        
        username = user[0]
        
        # 시작 메시지
        await websocket.send_json({
            "status": "ready",
            "message": f"{username}님의 센서 측정을 시작합니다",
            "user_id": user_id,
            "username": username
        })
        
        await asyncio.sleep(1)
        
        # 센서 초기화
        await websocket.send_json({
            "status": "initializing",
            "message": "센서 초기화 중...",
            "progress": 0
        })
        
        # 비동기로 센서 측정
        loop = asyncio.get_event_loop()
        
        # 온도 측정
        await websocket.send_json({
            "status": "measuring_temperature",
            "message": "체온 측정 중...",
            "progress": 10
        })
        
        sensor_manager = SensorManager(temp_address=0x3A, heart_channel=0)
        
        # 온도 측정 (5회 평균)
        temps = []
        for i in range(5):
            temp = await loop.run_in_executor(None, sensor_manager.read_temperature, 1)
            if temp:
                temps.append(temp)
                await websocket.send_json({
                    "status": "measuring_temperature",
                    "message": f"체온 측정 중... ({i+1}/5)",
                    "progress": 10 + (i+1) * 5,
                    "current_value": temp
                })
            await asyncio.sleep(0.2)
        
        temperature = sum(temps) / len(temps) if temps else 36.5
        
        await websocket.send_json({
            "status": "temperature_complete",
            "message": f"체온 측정 완료: {temperature:.1f}°C",
            "progress": 35,
            "temperature": round(temperature, 1)
        })
        
        await asyncio.sleep(0.5)
        
        # 심박수 측정 시작
        await websocket.send_json({
            "status": "measuring_heartrate",
            "message": "심박수 측정 중... (15초 소요)",
            "progress": 40
        })
        
        # 심박수 측정 (실시간 진행률 전송)
        duration = 15
        samples = []
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
            
            # 센서 값 읽기
            value = await loop.run_in_executor(None, sensor_manager.heart_sensor.read_adc)
            samples.append(value)
            
            # 진행률 계산 (40% ~ 90%)
            progress = 40 + int((elapsed / duration) * 50)
            
            # 실시간 전송 (0.5초마다)
            if len(samples) % 50 == 0:  # 100Hz 샘플링이므로 50개 = 0.5초
                await websocket.send_json({
                    "status": "measuring_heartrate",
                    "message": f"심박수 측정 중... {elapsed:.1f}/{duration}초",
                    "progress": progress,
                    "current_value": value,
                    "elapsed": round(elapsed, 1)
                })
            
            await asyncio.sleep(0.01)
        
        # 심박수 계산
        await websocket.send_json({
            "status": "calculating",
            "message": "심박수 분석 중...",
            "progress": 90
        })
        
        # 심박수 분석 (기존 로직)
        mean_value = sum(samples) / len(samples) if samples else 0
        std_value = (sum((x - mean_value) ** 2 for x in samples) / len(samples)) ** 0.5 if samples else 0
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
        
        heart_rate = 70  # 기본값
        if beats > 1 and beat_intervals:
            avg_interval = sum(beat_intervals) / len(beat_intervals)
            heart_rate = int(60 / avg_interval) if avg_interval > 0 else 70
        
        sensor_manager.close()
        
        # DB 저장
        await websocket.send_json({
            "status": "saving",
            "message": "데이터 저장 중...",
            "progress": 95
        })
        
        update_query = """
            UPDATE users 
            SET heart_rate = %s, temperature = %s, last_measured_at = NOW()
            WHERE user_id = %s
        """
        cursor.execute(update_query, (heart_rate, temperature, user_id))
        connection.commit()
        
        # 완료
        await websocket.send_json({
            "status": "complete",
            "message": f"{username}님 측정 완료!",
            "progress": 100,
            "result": {
                "user_id": user_id,
                "username": username,
                "heart_rate": heart_rate,
                "temperature": round(temperature, 1)
            }
        })
        
        cursor.close()
        connection.close()
        
    except WebSocketDisconnect:
        print(f"웹소켓 연결 끊김: user_id={user_id}")
    except Exception as e:
        print(f"센서 측정 오류: {e}")
        await websocket.send_json({
            "status": "error",
            "message": f"오류 발생: {str(e)}"
        })
    finally:
        await websocket.close()


@router.websocket("/ws/monitor/{user_id}")
async def websocket_monitor_sensor(websocket: WebSocket, user_id: int):
    """
    웹소켓으로 센서 값 실시간 모니터링 (측정 없이 관찰만)
    
    실시간 전송 데이터:
    - heart_rate_raw: 실시간 심박 센서 값
    - temperature_raw: 실시간 온도 센서 값
    - timestamp: 타임스탬프
    """
    await websocket.accept()
    
    try:
        await websocket.send_json({
            "status": "connected",
            "message": "센서 모니터링 시작"
        })
        
        sensor_manager = SensorManager(temp_address=0x3A, heart_channel=0)
        loop = asyncio.get_event_loop()
        
        while True:
            # 심박 센서 값
            heart_value = await loop.run_in_executor(
                None, 
                sensor_manager.heart_sensor.read_adc
            )
            
            # 온도 센서 값
            temp_value = await loop.run_in_executor(
                None,
                sensor_manager.temp_sensor.read_object_temp
            )
            
            # 실시간 전송
            await websocket.send_json({
                "heart_rate_raw": heart_value,
                "temperature_raw": temp_value,
                "timestamp": asyncio.get_event_loop().time()
            })
            
            await asyncio.sleep(0.1)  # 10Hz
            
    except WebSocketDisconnect:
        print("모니터링 중단")
        sensor_manager.close()
    except Exception as e:
        print(f"모니터링 오류: {e}")
        await websocket.send_json({
            "status": "error",
            "message": str(e)
        })
    finally:
        sensor_manager.close()
        await websocket.close()
def get_sensor_data(user_id: int, connection = Depends(get_db)):
    """특정 사용자의 센서 데이터 조회"""
    try:
        cursor = connection.cursor()
        
        query = """
            SELECT user_id, username, mbti, heart_rate, temperature, profile_image_url
            FROM users
            WHERE user_id = %s
        """
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        return {
            "user_id": result[0],
            "username": result[1],
            "mbti": result[2],
            "heart_rate": result[3],
            "temperature": result[4],
            "profile_image_url": result[5]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("/measure-sensor/{user_id}")
def measure_and_update_sensor(user_id: int, auto_calculate: bool = True, connection = Depends(get_db)):
    """실제 센서로 측정 후 DB 업데이트 및 자동 매칭 계산"""
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        username = user[0]
        print(f"\n{'='*60}")
        print(f"{username} (ID: {user_id})님의 센서 측정 시작")
        print(f"{'='*60}")
        
        sensor_manager = SensorManager(temp_address=0x3A, heart_channel=0)
        sensor_data = sensor_manager.read_sensors()
        sensor_manager.close()
        
        print(f"측정 완료: 심박수 {sensor_data['heart_rate']} BPM, 체온 {sensor_data['temperature']}°C")
    
        update_query = """
            UPDATE users 
            SET heart_rate = %s, temperature = %s, last_measured_at = NOW()
            WHERE user_id = %s
        """
        cursor.execute(update_query, (
            sensor_data['heart_rate'],
            sensor_data['temperature'],
            user_id
        ))
        connection.commit()
        
        # 자동 매칭 계산
        match_result = None
        if auto_calculate:
            print(f"\n운명의 상대 계산 중...")
            # 해당 사용자의 매칭만 다시 계산
            match_result = recalculate_user_matches(user_id, cursor, connection)
        
        cursor.close()
        
        response = {
            "success": True,
            "message": f"{username}님의 센서 데이터가 측정되고 저장되었습니다",
            "user_id": user_id,
            "username": username,
            "measured_data": {
                "heart_rate": sensor_data['heart_rate'],
                "temperature": sensor_data['temperature']
            }
        }
        
        if match_result:
            response["matching_updated"] = True
            response["top_matches"] = match_result
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        print(f"오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"센서 측정 오류: {str(e)}")


def recalculate_user_matches(user_id: int, cursor, connection):
    """특정 사용자의 매칭만 다시 계산 (내부 함수)"""
    try:
        # 현재 사용자 정보
        cursor.execute("""
            SELECT user_id, mbti, heart_rate, temperature
            FROM users
            WHERE user_id = %s
        """, (user_id,))
        current_user = cursor.fetchone()
        
        if not current_user:
            return None
        
        user_mbti = current_user[1]
        user_heart_rate = current_user[2] or 70
        user_temperature = current_user[3] or 36.5
        
        # 다른 사용자들
        cursor.execute("""
            SELECT user_id, mbti, heart_rate, temperature
            FROM users
            WHERE user_id != %s
        """, (user_id,))
        other_users = cursor.fetchall()
        
        if len(other_users) < 1:
            return None
        
        # 궁합 계산
        candidates = []
        for other_user in other_users:
            compatibility = calculate_total_compatibility(
                user_mbti, other_user[1],
                user_heart_rate, other_user[2] or 70,
                user_temperature, other_user[3] or 36.5
            )
            candidates.append({
                "user_id": other_user[0],
                "score": compatibility["total_score"]
            })
        
        # 상위 2명
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_matches = candidates[:2]
        
        # 기존 매칭 삭제
        cursor.execute("DELETE FROM fated_matches WHERE user_id = %s", (user_id,))
        
        # 새 매칭 저장
        for match in top_matches:
            cursor.execute("""
                INSERT INTO fated_matches (user_id, matched_user_id, match_score)
                VALUES (%s, %s, %s)
            """, (user_id, match["user_id"], match["score"]))
        
        connection.commit()
        
        return [{"user_id": m["user_id"], "score": m["score"]} for m in top_matches]
        
    except Exception as e:
        print(f"매칭 계산 오류: {e}")
        return None


@router.post("/measure-all-users")
def measure_all_users(connection = Depends(get_db)):
    """모든 사용자의 센서를 순차적으로 측정"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT user_id, username FROM users ORDER BY user_id")
        users = cursor.fetchall()
        
        if not users:
            cursor.close()
            raise HTTPException(status_code=404, detail="사용자가 없습니다")
        
        results = []
        
        for i, user in enumerate(users, 1):
            user_id = user[0]
            username = user[1]
            
            print(f"\n{'='*60}")
            print(f"[{i}/{len(users)}] {username} (ID: {user_id})님 측정 중...")
            print(f"{'='*60}")
            print("센서에 손을 올려주세요...")
            
            import time
            for countdown in range(3, 0, -1):
                print(f"{countdown}초 후 측정 시작...")
                time.sleep(1)
            
            sensor_manager = SensorManager(temp_address=0x3A, heart_channel=0)
            sensor_data = sensor_manager.read_sensors()
            sensor_manager.close()
            
            update_query = """
                UPDATE users 
                SET heart_rate = %s, temperature = %s, last_measured_at = NOW()
                WHERE user_id = %s
            """
            cursor.execute(update_query, (
                sensor_data['heart_rate'],
                sensor_data['temperature'],
                user_id
            ))
            
            results.append({
                "user_id": user_id,
                "username": username,
                "heart_rate": sensor_data['heart_rate'],
                "temperature": sensor_data['temperature']
            })
            
            print(f"✓ {username}님 측정 완료\n")
            
            if i < len(users):
                print("다음 사용자 준비 중...\n")
                time.sleep(2)
        
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": f"총 {len(users)}명의 센서 데이터가 측정되었습니다",
            "total_users": len(users),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"센서 측정 오류: {str(e)}")