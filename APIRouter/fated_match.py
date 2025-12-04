from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os
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
            SET heart_rate = %s, temperature = %s
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


@router.post("/calculate-all")
def calculate_all_matches(connection = Depends(get_db)):
    """모든 사용자의 운명의 상대를 한 번에 계산"""
    try:
        cursor = connection.cursor()
        
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


@router.get("/sensor/{user_id}")
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
def measure_and_update_sensor(user_id: int, connection = Depends(get_db)):
    """실제 센서로 측정 후 DB 업데이트"""
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
            SET heart_rate = %s, temperature = %s
            WHERE user_id = %s
        """
        cursor.execute(update_query, (
            sensor_data['heart_rate'],
            sensor_data['temperature'],
            user_id
        ))
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": f"{username}님의 센서 데이터가 측정되고 저장되었습니다",
            "user_id": user_id,
            "username": username,
            "measured_data": {
                "heart_rate": sensor_data['heart_rate'],
                "temperature": sensor_data['temperature']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        print(f"오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"센서 측정 오류: {str(e)}")


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
                SET heart_rate = %s, temperature = %s
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