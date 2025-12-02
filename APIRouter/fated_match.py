from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sensors.sensor_reader import SensorManager
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
    """
    센서 데이터 업데이트 (심박수, 온도)
    """
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
def get_fated_matches(user_id: int, connection = Depends(get_db)):
    """
    특정 사용자의 운명의 상대 2명 조회
    MBTI + 심박수 + 온도 기반 궁합 계산
    """
    try:
        cursor = connection.cursor()
        
        # 현재 사용자 정보 가져오기
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
        
        current_mbti = current_user[2]
        current_heart_rate = current_user[4] or 70
        current_temperature = current_user[5] or 36.5
        
        # 다른 모든 사용자 가져오기
        candidates_query = """
            SELECT user_id, username, mbti, profile_image_url, heart_rate, temperature
            FROM users
            WHERE user_id != %s
        """
        cursor.execute(candidates_query, (user_id,))
        all_candidates = cursor.fetchall()
        
        if len(all_candidates) < 2:
            cursor.close()
            raise HTTPException(status_code=400, detail="다른 사용자가 충분하지 않습니다")
        
        # 모든 후보와 궁합 계산
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
        
        # 점수 순으로 정렬
        candidates_with_scores.sort(key=lambda x: x["compatibility_score"], reverse=True)
        
        # 상위 2명 선택
        top_matches = candidates_with_scores[:2]
        
        # DB에 매칭 결과 저장
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
                "mbti": current_mbti,
                "heart_rate": current_heart_rate,
                "temperature": current_temperature
            },
            "fated_matches": top_matches
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("/calculate-all")
def calculate_all_matches(connection = Depends(get_db)):
    """
    모든 사용자(8명)의 운명의 상대를 한 번에 계산
    """
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
            raise HTTPException(status_code=400, detail="최소 2명 이상의 사용자가 필요합니다")
        
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


def calculate_total_compatibility(
    mbti1: str, mbti2: str,
    heart_rate1: int, heart_rate2: int,
    temperature1: float, temperature2: float
) -> dict:
    """
    종합 궁합 점수 계산
    - MBTI 궁합: 50%
    - 심박수 유사도: 30%
    - 체온 유사도: 20%
    """
    
    mbti_score = calculate_mbti_compatibility(mbti1, mbti2)
    
    # 심박수 유사도
    heart_rate_diff = abs(heart_rate1 - heart_rate2)
    heart_rate_score = 100-heart_rate_diff*2
    
    # 체온 유사도
    temperature_diff = abs(temperature1 - temperature2)
    temperature_score = 100-temperature_diff*100
    
    total_score = int(
        (mbti_score * 0.2) +
        (heart_rate_score * 0.5) +
        (temperature_score * 0.3)
    )
    
    return {
        "total_score": total_score,
        "mbti_score": mbti_score,
        "heart_rate_score": int(heart_rate_score),
        "temperature_score": int(temperature_score)
    }


def calculate_mbti_compatibility(mbti1: str, mbti2: str) -> int:
    """
    MBTI 궁합 점수 계산
    """
    compatibility_map = {
        "INFJ": {"ENFP": 100, "ENTP": 89, "INFP": 86, "INTJ": 75, "INTP": 86, "ENFJ": 89, "ENTJ": 89, "ISFJ": 50, "ISFP": 61, "ISTJ": 50, "ISTP": 61, "ESFJ": 64, "ESFP": 75, "ESTJ": 64, "ESTP": 75},
        "INFP": {"ENFJ": 100, "ENTJ": 89, "INFJ": 86, "INTJ": 86, "INTP": 75, "ENFP": 89, "ENTP": 89, "ISFJ": 61, "ISFP": 50, "ISTJ": 61, "ISTP": 50, "ESFJ": 75, "ESFP": 64, "ESTJ": 75, "ESTP": 64},        
        "ENFJ": {"INFP": 100, "INTP": 100, "INFJ": 89, "INTJ": 89, "ENFP": 100, "ENTP": 100, "ISFJ": 64, "ISFP": 75, "ISTJ": 64, "ISTP": 75, "ESFJ": 100, "ESFP": 89, "ESTJ": 100, "ESTP": 89},        
        "ENFP": {"INFJ": 100, "INTJ": 100, "INFP": 89, "INTP": 89, "ENFJ": 100, "ENTJ": 100, "ISFJ": 75, "ISFP": 64, "ISTJ": 75, "ISTP": 64, "ESFJ": 89, "ESFP": 100, "ESTJ": 89, "ESTP": 100},        
        "INTJ": {"ENFP": 100, "ENTP": 100, "INFJ": 75, "INFP": 86, "INTP": 86, "ENFJ": 89, "ENTJ": 89, "ISFJ": 50, "ISFP": 61, "ISTJ": 50, "ISTP": 61, "ESFJ": 64, "ESFP": 75, "ESTJ": 64, "ESTP": 75},        
        "INTP": {"ENFJ": 100, "ENTJ": 100, "INFJ": 86, "INFP": 75, "INTJ": 86, "ENFP": 89, "ENTP": 89, "ISFJ": 61, "ISFP": 50, "ISTJ": 61, "ISTP": 50, "ESFJ": 75, "ESFP": 64, "ESTJ": 75, "ESTP": 64},        
        "ENTJ": {"INFP": 100, "INTP": 100, "INFJ": 89, "INTJ": 89, "ENFJ": 100, "ENTP": 100, "ISFJ": 64, "ISFP": 75, "ISTJ": 64, "ISTP": 75, "ESFJ": 100, "ESFP": 89, "ESTJ": 100, "ESTP": 89},        
        "ENTP": {"INFJ": 100, "INTJ": 100, "INFP": 89, "INTP": 89, "ENFJ": 100, "ENTJ": 100, "ISFJ": 75, "ISFP": 64, "ISTJ": 75, "ISTP": 64, "ESFJ": 89, "ESFP": 100, "ESTJ": 89, "ESTP": 100},        
        "ISFJ": {"ESFP": 100, "ESTP": 89, "ISFP": 86, "ISTJ": 75, "ISTP": 86, "ESFJ": 89, "ESTJ": 89, "INFJ": 50, "INFP": 61, "INTJ": 50, "INTP": 61, "ENFJ": 64, "ENFP": 75, "ENTJ": 64, "ENTP": 75},
        "ISFP": {"ESFJ": 100, "ESTJ": 89, "ISFJ": 86, "ISTJ": 86, "ISTP": 75, "ESFP": 89, "ESTP": 89, "INFJ": 61, "INFP": 50, "INTJ": 61, "INTP": 50, "ENFJ": 75, "ENFP": 64, "ENTJ": 75, "ENTP": 64},
        "ESFJ": {"ISFP": 100, "ISTP": 100, "ISFJ": 89, "ISTJ": 89, "ESFP": 100, "ESTP": 100, "INFJ": 64, "INFP": 75, "INTJ": 64, "INTP": 75, "ENFJ": 100, "ENFP": 89, "ENTJ": 100, "ENTP": 89},        
        "ESFP": {"ISFJ": 100, "ISTJ": 100, "ISFP": 89, "ISTP": 89, "ESFJ": 100, "ESTJ": 100, "INFJ": 75, "INFP": 64, "INTJ": 75, "INTP": 64, "ENFJ": 89, "ENFP": 100, "ENTJ": 89, "ENTP": 100},        
        "ISTJ": {"ESFP": 100, "ESTP": 89, "ISFJ": 75, "ISFP": 86, "ISTP": 86, "ESFJ": 89, "ESTJ": 89, "INFJ": 50, "INFP": 61, "INTJ": 50, "INTP": 61, "ENFJ": 64, "ENFP": 75, "ENTJ": 64, "ENTP": 75},        
        "ISTP": {"ESFJ": 100, "ESTJ": 100, "ISFJ": 86, "ISFP": 75, "ISTJ": 86, "ESFP": 89, "ESTP": 89, "INFJ": 61, "INFP": 50, "INTJ": 61, "INTP": 50, "ENFJ": 75, "ENFP": 64, "ENTJ": 75, "ENTP": 64},        
        "ESTJ": {"ISFP": 100, "ISTP": 100, "ISFJ": 89, "ISTJ": 89, "ESFJ": 100, "ESTP": 100, "INFJ": 64, "INFP": 75, "INTJ": 64, "INTP": 75, "ENFJ": 100, "ENFP": 89, "ENTJ": 100, "ENTP": 89},        
        "ESTP": {"ISFJ": 100, "ISTJ": 100, "ISFP": 89, "ISTP": 89, "ESFJ": 100, "ESTJ": 100, "INFJ": 75, "INFP": 64, "INTJ": 75, "INTP": 64, "ENFJ": 89, "ENFP": 100, "ENTJ": 89, "ENTP": 100},
    }
    
    if mbti1 in compatibility_map and mbti2 in compatibility_map[mbti1]:
        return compatibility_map[mbti1][mbti2]
    if mbti1 == mbti2:
        return 75
    return 60
@router.get("/sensor/{user_id}")
def get_sensor_data(user_id: int, connection = Depends(get_db)):
    """
    특정 사용자의 센서 데이터 조회
    """
    try:
        cursor = connection.cursor()
        
        query = """
            SELECT user_id, username, heart_rate, temperature
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
            "heart_rate": result[2],
            "temperature": result[3]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")
@router.post("/measure-sensor/{user_id}")
def measure_and_update_sensor(user_id: int, connection = Depends(get_db)):
    """
    실제 센서로 측정 후 DB 업데이트
    
    사용법:
    POST /api/fated-match/measure-sensor/1
    -> user_id 1번의 센서 데이터를 측정하고 저장
    """
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
        
        sensor_manager = SensorManager(temp_address=0x3A, heart_channel=1)
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
    """
    모든 사용자의 센서를 순차적으로 측정
    
    사용법:
    POST /api/fated-match/measure-all-users
    -> 모든 사용자의 센서 데이터를 차례로 측정
    """
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
            sensor_manager = SensorManager(temp_address=0x3A, heart_channel=1)
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