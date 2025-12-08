from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/confessions", tags=["confessions"])

class ConfessionCreate(BaseModel):
    from_user_id: int
    to_user_id: int
    message: Optional[str] = None

class ConfessionUpdate(BaseModel):
    status: str  # 'pending', 'accepted', 'rejected'
    couple_name: Optional[str] = None  # 수락 시 커플명 (선택)

def get_db():
    from config import engine
    connection = engine.raw_connection()
    try:
        yield connection
    finally:
        connection.close()


@router.post("")
def create_confession(confession: ConfessionCreate, connection = Depends(get_db)):
    """고백 전송"""
    try:
        cursor = connection.cursor()
        
        # 보내는 사람 확인
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (confession.from_user_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="보내는 사용자를 찾을 수 없습니다")
        
        # 받는 사람 확인
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (confession.to_user_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="받는 사용자를 찾을 수 없습니다")
        
        # 자기 자신에게 고백 방지
        if confession.from_user_id == confession.to_user_id:
            cursor.close()
            raise HTTPException(status_code=400, detail="자기 자신에게 고백할 수 없습니다")
        
        # 이미 고백한 적이 있는지 확인
        cursor.execute("""
            SELECT confession_id FROM confessions 
            WHERE from_user_id = %s AND to_user_id = %s AND status = 'pending'
        """, (confession.from_user_id, confession.to_user_id))
        
        if cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=400, detail="이미 고백을 보냈습니다")
        
        # 고백 생성
        insert_query = """
            INSERT INTO confessions (from_user_id, to_user_id, message, status)
            VALUES (%s, %s, %s, 'pending')
        """
        cursor.execute(insert_query, (
            confession.from_user_id,
            confession.to_user_id,
            confession.message
        ))
        connection.commit()
        confession_id = cursor.lastrowid
        
        # 생성된 고백 조회
        cursor.execute("""
            SELECT c.confession_id, c.from_user_id, u1.username as from_username,
                   c.to_user_id, u2.username as to_username, c.status, c.message, c.created_at
            FROM confessions c
            JOIN users u1 ON c.from_user_id = u1.user_id
            JOIN users u2 ON c.to_user_id = u2.user_id
            WHERE c.confession_id = %s
        """, (confession_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return {
            "success": True,
            "message": "고백이 전송되었습니다",
            "confession": {
                "confession_id": result[0],
                "from_user_id": result[1],
                "from_username": result[2],
                "to_user_id": result[3],
                "to_username": result[4],
                "status": result[5],
                "message": result[6],
                "created_at": result[7].isoformat() if result[7] else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/received/{user_id}")
def get_received_confessions(user_id: int, connection = Depends(get_db)):
    """받은 고백 목록 조회"""
    try:
        cursor = connection.cursor()
        
        query = """
            SELECT c.confession_id, c.from_user_id, u1.username as from_username,
                   u1.mbti as from_mbti, u1.profile_image_url as from_profile,
                   c.status, c.message, c.created_at
            FROM confessions c
            JOIN users u1 ON c.from_user_id = u1.user_id
            WHERE c.to_user_id = %s
            ORDER BY c.created_at DESC
        """
        cursor.execute(query, (user_id,))
        results = cursor.fetchall()
        cursor.close()
        
        confessions = [
            {
                "confession_id": row[0],
                "from_user_id": row[1],
                "from_username": row[2],
                "from_mbti": row[3],
                "from_profile_image_url": row[4],
                "status": row[5],
                "message": row[6],
                "created_at": row[7].isoformat() if row[7] else None
            }
            for row in results
        ]
        
        return {
            "user_id": user_id,
            "count": len(confessions),
            "confessions": confessions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/sent/{user_id}")
def get_sent_confessions(user_id: int, connection = Depends(get_db)):
    """보낸 고백 목록 조회"""
    try:
        cursor = connection.cursor()
        
        query = """
            SELECT c.confession_id, c.to_user_id, u2.username as to_username,
                   u2.mbti as to_mbti, u2.profile_image_url as to_profile,
                   c.status, c.message, c.created_at
            FROM confessions c
            JOIN users u2 ON c.to_user_id = u2.user_id
            WHERE c.from_user_id = %s
            ORDER BY c.created_at DESC
        """
        cursor.execute(query, (user_id,))
        results = cursor.fetchall()
        cursor.close()
        
        confessions = [
            {
                "confession_id": row[0],
                "to_user_id": row[1],
                "to_username": row[2],
                "to_mbti": row[3],
                "to_profile_image_url": row[4],
                "status": row[5],
                "message": row[6],
                "created_at": row[7].isoformat() if row[7] else None
            }
            for row in results
        ]
        
        return {
            "user_id": user_id,
            "count": len(confessions),
            "confessions": confessions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.put("/{confession_id}")
def update_confession_status(
    confession_id: int,
    update: ConfessionUpdate,
    connection = Depends(get_db)
):
    """고백 수락/거절"""
    try:
        cursor = connection.cursor()
        
        # 고백 존재 확인
        cursor.execute("SELECT * FROM confessions WHERE confession_id = %s", (confession_id,))
        confession = cursor.fetchone()
        
        if not confession:
            cursor.close()
            raise HTTPException(status_code=404, detail="고백을 찾을 수 없습니다")
        
        # 상태 검증
        if update.status not in ['pending', 'accepted', 'rejected']:
            cursor.close()
            raise HTTPException(status_code=400, detail="올바른 상태를 입력하세요 (pending, accepted, rejected)")
        
        # 상태 업데이트
        cursor.execute("""
            UPDATE confessions 
            SET status = %s 
            WHERE confession_id = %s
        """, (update.status, confession_id))
        connection.commit()
        
        # 수락된 경우 커플 생성
        if update.status == 'accepted':
            from_user_id = confession[1]
            to_user_id = confession[2]
            
            # 궁합 점수 계산
            cursor.execute("""
                SELECT mbti, heart_rate, temperature 
                FROM users WHERE user_id = %s
            """, (from_user_id,))
            user1 = cursor.fetchone()
            
            cursor.execute("""
                SELECT mbti, heart_rate, temperature 
                FROM users WHERE user_id = %s
            """, (to_user_id,))
            user2 = cursor.fetchone()
            
            # compatibility 함수 import
            from .compatibility import calculate_total_compatibility
            
            compatibility = calculate_total_compatibility(
                user1[0], user2[0],
                user1[1] or 70, user2[1] or 70,
                user1[2] or 36.5, user2[2] or 36.5
            )
            
            # 커플명 기본값 설정
            couple_name = update.couple_name
            if not couple_name:
                # 커플명이 없으면 자동 생성
                cursor.execute("SELECT username FROM users WHERE user_id = %s", (from_user_id,))
                username1 = cursor.fetchone()[0]
                cursor.execute("SELECT username FROM users WHERE user_id = %s", (to_user_id,))
                username2 = cursor.fetchone()[0]
                couple_name = f"{username1} ❤️ {username2}"
            
            # couple_ranking에 추가
            cursor.execute("""
                INSERT INTO couple_ranking (user_a_id, user_b_id, score, couple_name)
                VALUES (%s, %s, %s, %s)
            """, (
                min(from_user_id, to_user_id), 
                max(from_user_id, to_user_id), 
                compatibility['total_score'],
                couple_name
            ))
            connection.commit()
        
        # 업데이트된 고백 조회
        cursor.execute("""
            SELECT c.confession_id, c.from_user_id, u1.username as from_username,
                   c.to_user_id, u2.username as to_username, c.status, c.message, c.created_at
            FROM confessions c
            JOIN users u1 ON c.from_user_id = u1.user_id
            JOIN users u2 ON c.to_user_id = u2.user_id
            WHERE c.confession_id = %s
        """, (confession_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return {
            "success": True,
            "message": f"고백이 {update.status}(으)로 업데이트되었습니다",
            "confession": {
                "confession_id": result[0],
                "from_user_id": result[1],
                "from_username": result[2],
                "to_user_id": result[3],
                "to_username": result[4],
                "status": result[5],
                "message": result[6],
                "created_at": result[7].isoformat() if result[7] else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.delete("/{confession_id}")
def delete_confession(confession_id: int, connection = Depends(get_db)):
    """고백 삭제"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT * FROM confessions WHERE confession_id = %s", (confession_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="고백을 찾을 수 없습니다")
        
        cursor.execute("DELETE FROM confessions WHERE confession_id = %s", (confession_id,))
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": "고백이 삭제되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/{confession_id}")
def get_confession(confession_id: int, connection = Depends(get_db)):
    """특정 고백 상세 조회"""
    try:
        cursor = connection.cursor()
        
        query = """
            SELECT c.confession_id, c.from_user_id, u1.username as from_username,
                   u1.mbti as from_mbti, u1.profile_image_url as from_profile,
                   c.to_user_id, u2.username as to_username,
                   u2.mbti as to_mbti, u2.profile_image_url as to_profile,
                   c.status, c.message, c.created_at
            FROM confessions c
            JOIN users u1 ON c.from_user_id = u1.user_id
            JOIN users u2 ON c.to_user_id = u2.user_id
            WHERE c.confession_id = %s
        """
        cursor.execute(query, (confession_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="고백을 찾을 수 없습니다")
        
        return {
            "confession_id": result[0],
            "from_user": {
                "user_id": result[1],
                "username": result[2],
                "mbti": result[3],
                "profile_image_url": result[4]
            },
            "to_user": {
                "user_id": result[5],
                "username": result[6],
                "mbti": result[7],
                "profile_image_url": result[8]
            },
            "status": result[9],
            "message": result[10],
            "created_at": result[11].isoformat() if result[11] else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")