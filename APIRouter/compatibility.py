from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/compatibility", tags=["compatibility"])

class CompatibilityRequest(BaseModel):
    user_id_1: int
    user_id_2: int

class ManualCompatibilityRequest(BaseModel):
    mbti_1: str
    mbti_2: str
    heart_rate_1: Optional[int] = 70
    heart_rate_2: Optional[int] = 70
    temperature_1: Optional[float] = 36.5
    temperature_2: Optional[float] = 36.5

def get_db():
    from config import engine
    connection = engine.raw_connection()
    try:
        yield connection
    finally:
        connection.close()


def calculate_mbti_compatibility(mbti1: str, mbti2: str) -> int:
    """MBTI 궁합 점수 계산"""
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
    if heart_rate_diff <= 5:
        heart_rate_score = 100
    elif heart_rate_diff <= 10:
        heart_rate_score = 85
    elif heart_rate_diff <= 15:
        heart_rate_score = 70
    elif heart_rate_diff <= 20:
        heart_rate_score = 55
    else:
        heart_rate_score = max(40, 100 - (heart_rate_diff * 2))
    
    # 체온 유사도
    temperature_diff = abs(temperature1 - temperature2)
    if temperature_diff <= 0.3:
        temperature_score = 100
    elif temperature_diff <= 0.6:
        temperature_score = 85
    elif temperature_diff <= 1.0:
        temperature_score = 70
    elif temperature_diff <= 1.5:
        temperature_score = 55
    else:
        temperature_score = max(40, 100 - (temperature_diff * 30))
    
    # 종합 점수
    total_score = int(
        (mbti_score * 0.5) +
        (heart_rate_score * 0.3) +
        (temperature_score * 0.2)
    )
    
    return {
        "total_score": total_score,
        "mbti_score": mbti_score,
        "heart_rate_score": int(heart_rate_score),
        "temperature_score": int(temperature_score)
    }


@router.post("/calculate")
def calculate_compatibility_by_users(
    request: CompatibilityRequest,
    connection = Depends(get_db)
):
    """두 사용자의 궁합 계산 (DB에서 정보 조회)"""
    try:
        cursor = connection.cursor()
        
        # 사용자 1 정보 조회
        cursor.execute("""
            SELECT user_id, username, mbti, profile_image_url, heart_rate, temperature
            FROM users WHERE user_id = %s
        """, (request.user_id_1,))
        user1 = cursor.fetchone()
        
        if not user1:
            cursor.close()
            raise HTTPException(status_code=404, detail=f"사용자 {request.user_id_1}를 찾을 수 없습니다")
        
        # 사용자 2 정보 조회
        cursor.execute("""
            SELECT user_id, username, mbti, profile_image_url, heart_rate, temperature
            FROM users WHERE user_id = %s
        """, (request.user_id_2,))
        user2 = cursor.fetchone()
        
        if not user2:
            cursor.close()
            raise HTTPException(status_code=404, detail=f"사용자 {request.user_id_2}를 찾을 수 없습니다")
        
        cursor.close()
        
        # 궁합 계산
        compatibility = calculate_total_compatibility(
            user1[2], user2[2],  # MBTI
            user1[4] or 70, user2[4] or 70,  # 심박수
            user1[5] or 36.5, user2[5] or 36.5  # 체온
        )
        
        return {
            "user_1": {
                "user_id": user1[0],
                "username": user1[1],
                "mbti": user1[2],
                "profile_image_url": user1[3],
                "heart_rate": user1[4],
                "temperature": float(user1[5]) if user1[5] else None
            },
            "user_2": {
                "user_id": user2[0],
                "username": user2[1],
                "mbti": user2[2],
                "profile_image_url": user2[3],
                "heart_rate": user2[4],
                "temperature": float(user2[5]) if user2[5] else None
            },
            "compatibility": compatibility
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("/calculate-manual")
def calculate_compatibility_manual(request: ManualCompatibilityRequest):
    """수동으로 입력한 데이터로 궁합 계산 (DB 조회 없음)"""
    try:
        # MBTI 유효성 검사
        valid_mbti = [
            "ISTJ", "ISFJ", "INFJ", "INTJ",
            "ISTP", "ISFP", "INFP", "INTP",
            "ESTP", "ESFP", "ENFP", "ENTP",
            "ESTJ", "ESFJ", "ENFJ", "ENTJ"
        ]
        
        if request.mbti_1.upper() not in valid_mbti:
            raise HTTPException(status_code=400, detail=f"올바른 MBTI를 입력하세요: {request.mbti_1}")
        
        if request.mbti_2.upper() not in valid_mbti:
            raise HTTPException(status_code=400, detail=f"올바른 MBTI를 입력하세요: {request.mbti_2}")
        
        # 궁합 계산
        compatibility = calculate_total_compatibility(
            request.mbti_1.upper(),
            request.mbti_2.upper(),
            request.heart_rate_1,
            request.heart_rate_2,
            request.temperature_1,
            request.temperature_2
        )
        
        return {
            "input": {
                "mbti_1": request.mbti_1.upper(),
                "mbti_2": request.mbti_2.upper(),
                "heart_rate_1": request.heart_rate_1,
                "heart_rate_2": request.heart_rate_2,
                "temperature_1": request.temperature_1,
                "temperature_2": request.temperature_2
            },
            "compatibility": compatibility
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계산 오류: {str(e)}")


@router.get("/mbti/{mbti1}/{mbti2}")
def get_mbti_compatibility(mbti1: str, mbti2: str):
    """MBTI 궁합만 계산"""
    try:
        valid_mbti = [
            "ISTJ", "ISFJ", "INFJ", "INTJ",
            "ISTP", "ISFP", "INFP", "INTP",
            "ESTP", "ESFP", "ENFP", "ENTP",
            "ESTJ", "ESFJ", "ENFJ", "ENTJ"
        ]
        
        mbti1 = mbti1.upper()
        mbti2 = mbti2.upper()
        
        if mbti1 not in valid_mbti:
            raise HTTPException(status_code=400, detail=f"올바른 MBTI를 입력하세요: {mbti1}")
        
        if mbti2 not in valid_mbti:
            raise HTTPException(status_code=400, detail=f"올바른 MBTI를 입력하세요: {mbti2}")
        
        score = calculate_mbti_compatibility(mbti1, mbti2)
        
        # 점수에 따른 설명
        if score >= 90:
            description = "최고의 궁합! 환상의 커플입니다 💕"
        elif score >= 80:
            description = "매우 좋은 궁합! 서로를 잘 이해합니다 💝"
        elif score >= 70:
            description = "좋은 궁합! 노력하면 잘 맞을 수 있습니다 💗"
        elif score >= 60:
            description = "보통 궁합! 서로 이해하려는 노력이 필요합니다 💛"
        else:
            description = "조금 어려운 궁합! 하지만 사랑이 있다면 극복 가능합니다 💙"
        
        return {
            "mbti_1": mbti1,
            "mbti_2": mbti2,
            "score": score,
            "description": description
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계산 오류: {str(e)}")


@router.get("/mbti-chart")
def get_mbti_compatibility_chart():
    """모든 MBTI 궁합 차트 반환"""
    mbti_types = [
        "ISTJ", "ISFJ", "INFJ", "INTJ",
        "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP",
        "ESTJ", "ESFJ", "ENFJ", "ENTJ"
    ]
    
    chart = {}
    
    for mbti1 in mbti_types:
        chart[mbti1] = {}
        for mbti2 in mbti_types:
            chart[mbti1][mbti2] = calculate_mbti_compatibility(mbti1, mbti2)
    
    return {
        "mbti_types": mbti_types,
        "compatibility_chart": chart
    }