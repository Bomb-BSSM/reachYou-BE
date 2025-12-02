from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/users", tags=["users"])

class UserCreate(BaseModel):
    username: str
    mbti: str
    profile_image_url: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    mbti: Optional[str] = None
    profile_image_url: Optional[str] = None

def get_db():
    from config import engine
    connection = engine.raw_connection()
    try:
        yield connection
    finally:
        connection.close()

@router.post("")
def create_user(user: UserCreate, connection = Depends(get_db)):
    if not user.username:
        raise HTTPException(status_code=400, detail="사용자 이름을 입력해주세요")
    valid_mbti = [
        "ISTJ", "ISFJ", "INFJ", "INTJ",
        "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP",
        "ESTJ", "ESFJ", "ENFJ", "ENTJ"
    ]
    if user.mbti.upper() not in valid_mbti:
        raise HTTPException(status_code=400, detail="올바른 MBTI 유형을 입력해주세요")
    
    try:
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO users (username, mbti, profile_image_url)
            VALUES (%s, %s, %s)
        """
        cursor.execute(insert_query, (
            user.username,
            user.mbti.upper(),
            user.profile_image_url
        ))
        connection.commit()
        user_id = cursor.lastrowid
        select_query = "SELECT * FROM users WHERE user_id = %s"
        cursor.execute(select_query, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            return {
                "success": True,
                "message": "사용자가 생성되었습니다",
                "user": {
                    "user_id": result[0],
                    "username": result[1],
                    "mbti": result[2],
                    "profile_image_url": result[3]
                }
            }
        
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")

@router.get("")
def get_users(connection = Depends(get_db)):
    try:
        cursor = connection.cursor()
        
        select_query = "SELECT * FROM users"
        cursor.execute(select_query)
        results = cursor.fetchall()
        cursor.close()
        
        users = [
            {
                "user_id": row[0],
                "username": row[1],
                "mbti": row[2],
                "profile_image_url": row[3]
            }
            for row in results
        ]
        
        return {
            "count": len(users),
            "users": users
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")

@router.get("/{user_id}")
def get_user(user_id: int, connection = Depends(get_db)):
    try:
        cursor = connection.cursor()
        
        select_query = "SELECT * FROM users WHERE user_id = %s"
        cursor.execute(select_query, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        return {
            "user_id": result[0],
            "username": result[1],
            "mbti": result[2],
            "profile_image_url": result[3]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")

@router.get("/mbti/{mbti}")
def get_users_by_mbti(mbti: str, connection = Depends(get_db)):
    try:
        cursor = connection.cursor()
        
        select_query = "SELECT * FROM users WHERE mbti = %s"
        cursor.execute(select_query, (mbti.upper(),))
        results = cursor.fetchall()
        cursor.close()
        
        users = [
            {
                "user_id": row[0],
                "username": row[1],
                "mbti": row[2],
                "profile_image_url": row[3]
            }
            for row in results
        ]
        
        return {
            "mbti": mbti.upper(),
            "count": len(users),
            "users": users
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")

@router.put("/{user_id}")
def update_user(user_id: int, user_update: UserUpdate, connection = Depends(get_db)):
    try:
        cursor = connection.cursor()
        check_query = "SELECT * FROM users WHERE user_id = %s"
        cursor.execute(check_query, (user_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        update_fields = []
        update_values = []
        
        if user_update.username:
            update_fields.append("username = %s")
            update_values.append(user_update.username)
        
        if user_update.mbti:
            update_fields.append("mbti = %s")
            update_values.append(user_update.mbti.upper())
        
        if user_update.profile_image_url is not None:
            update_fields.append("profile_image_url = %s")
            update_values.append(user_update.profile_image_url)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다")
        update_values.append(user_id)
        update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = %s"
        cursor.execute(update_query, tuple(update_values))
        connection.commit()
        select_query = "SELECT * FROM users WHERE user_id = %s"
        cursor.execute(select_query, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        
        return {
            "success": True,
            "message": "사용자 정보가 수정되었습니다",
            "user": {
                "user_id": result[0],
                "username": result[1],
                "mbti": result[2],
                "profile_image_url": result[3]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")

@router.delete("/{user_id}")
def delete_user(user_id: int, connection = Depends(get_db)):
    try:
        cursor = connection.cursor()
        check_query = "SELECT * FROM users WHERE user_id = %s"
        cursor.execute(check_query, (user_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        delete_query = "DELETE FROM users WHERE user_id = %s"
        cursor.execute(delete_query, (user_id,))
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": "사용자가 삭제되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")

@router.get("/stats/mbti")
def get_mbti_stats(connection = Depends(get_db)):
    try:
        cursor = connection.cursor()
        count_query = "SELECT COUNT(*) FROM users"
        cursor.execute(count_query)
        total_users = cursor.fetchone()[0]
        stats_query = """
            SELECT mbti, COUNT(*) as count
            FROM users
            WHERE mbti IS NOT NULL
            GROUP BY mbti
            ORDER BY count DESC
        """
        cursor.execute(stats_query)
        results = cursor.fetchall()
        cursor.close()
        
        return {
            "total_users": total_users,
            "mbti_distribution": [
                {"mbti": row[0], "count": row[1]}
                for row in results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")