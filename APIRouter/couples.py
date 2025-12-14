from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/couples", tags=["couples"])

class CoupleCreate(BaseModel):
    user_a_id: int
    user_b_id: int
    couple_name: Optional[str] = None

class RatingCreate(BaseModel):
    rating: int
    comment: Optional[str] = None
    nickname: Optional[str] = "익명"

def get_db():
    from config import engine
    connection = engine.raw_connection()
    try:
        yield connection
    finally:
        connection.close()


@router.get("/ranking")
def get_couple_ranking(
    limit: int = 10,
    offset: int = 0,
    connection = Depends(get_db)
):
    """커플 랭킹 조회"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM couple_ranking")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_name = 'couple_ratings'
        """)
        has_ratings = cursor.fetchone()[0] > 0
        
        if has_ratings:
            query = """
                SELECT 
                    cr.couple_id,
                    cr.user_a_id,
                    u1.username,
                    u1.mbti,
                    u1.profile_image_url,
                    cr.user_b_id,
                    u2.username,
                    u2.mbti,
                    u2.profile_image_url,
                    cr.score,
                    cr.couple_name,
                    cr.created_at,
                    COALESCE(AVG(ratings.rating), 0) as average_rating,
                    COUNT(ratings.rating_id) as rating_count
                FROM couple_ranking cr
                JOIN users u1 ON cr.user_a_id = u1.user_id
                JOIN users u2 ON cr.user_b_id = u2.user_id
                LEFT JOIN couple_ratings ratings ON cr.couple_id = ratings.couple_id
                GROUP BY cr.couple_id, cr.user_a_id, u1.username, u1.mbti, u1.profile_image_url,
                         cr.user_b_id, u2.username, u2.mbti, u2.profile_image_url,
                         cr.score, cr.couple_name, cr.created_at
                ORDER BY average_rating DESC, rating_count DESC, cr.score DESC
                LIMIT %s OFFSET %s
            """
        else:
            query = """
                SELECT 
                    cr.couple_id,
                    cr.user_a_id,
                    u1.username,
                    u1.mbti,
                    u1.profile_image_url,
                    cr.user_b_id,
                    u2.username,
                    u2.mbti,
                    u2.profile_image_url,
                    cr.score,
                    cr.couple_name,
                    cr.created_at,
                    0 as average_rating,
                    0 as rating_count
                FROM couple_ranking cr
                JOIN users u1 ON cr.user_a_id = u1.user_id
                JOIN users u2 ON cr.user_b_id = u2.user_id
                ORDER BY cr.score DESC
                LIMIT %s OFFSET %s
            """
        
        cursor.execute(query, (limit, offset))
        couples = cursor.fetchall()
        
        ranking = []
        for idx, couple in enumerate(couples, start=offset + 1):
            ranking.append({
                "couple_id": couple[0],
                "rank": idx,
                "user_a": {
                    "user_id": couple[1],
                    "username": couple[2],
                    "mbti": couple[3],
                    "profile_image_url": couple[4]
                },
                "user_b": {
                    "user_id": couple[5],
                    "username": couple[6],
                    "mbti": couple[7],
                    "profile_image_url": couple[8]
                },
                "score": float(couple[9]) if couple[9] is not None else 0.0,
                "couple_name": couple[10],
                "average_rating": round(float(couple[12]), 2) if couple[12] else 0.0,
                "rating_count": int(couple[13]) if couple[13] else 0,
                "created_at": couple[11].isoformat() if couple[11] else None
            })
        
        cursor.close()
        
        return {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "ranking": ranking
        }
        
    except Exception as e:
        import traceback
        print("=" * 60)
        print("커플 랭킹 조회 오류:")
        print(traceback.format_exc())
        print("=" * 60)
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/{couple_id}")
def get_couple_detail(couple_id: int, connection = Depends(get_db)):
    """커플 상세 정보 조회"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT 
                cr.couple_id,
                cr.user_a_id,
                u1.username,
                u1.mbti,
                u1.profile_image_url,
                cr.user_b_id,
                u2.username,
                u2.mbti,
                u2.profile_image_url,
                cr.score,
                cr.couple_name,
                cr.created_at
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE cr.couple_id = %s
        """, (couple_id,))
        
        couple = cursor.fetchone()
        
        if not couple:
            cursor.close()
            raise HTTPException(status_code=404, detail="커플을 찾을 수 없습니다")
        
        current_score = couple[9] if couple[9] is not None else 0
        cursor.execute("""
            SELECT COUNT(*) + 1 FROM couple_ranking 
            WHERE score > %s
        """, (current_score,))
        rank = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_name = 'couple_ratings'
        """)
        has_ratings = cursor.fetchone()[0] > 0
        
        average_rating = 0.0
        rating_count = 0
        ratings_list = []
        
        if has_ratings:
            try:
                cursor.execute("""
                    SELECT AVG(rating), COUNT(*) 
                    FROM couple_ratings 
                    WHERE couple_id = %s
                """, (couple_id,))
                avg_result = cursor.fetchone()
                average_rating = round(float(avg_result[0]), 2) if avg_result[0] else 0.0
                rating_count = int(avg_result[1]) if avg_result[1] else 0
                
                cursor.execute("""
                    SELECT 
                        cr.rating,
                        cr.comment,
                        cr.created_at,
                        cr.nickname
                    FROM couple_ratings cr
                    WHERE cr.couple_id = %s
                    ORDER BY cr.created_at DESC
                """, (couple_id,))
                
                ratings = cursor.fetchall()
                for rating in ratings:
                    ratings_list.append({
                        "rating": rating[0],
                        "comment": rating[1],
                        "created_at": rating[2].isoformat() if rating[2] else None,
                        "nickname": rating[3] if rating[3] else "익명"
                    })
            except Exception as rating_error:
                print(f"⚠️ 별점 조회 중 오류: {rating_error}")
                import traceback
                traceback.print_exc()
        
        cursor.close()
        
        return {
            "couple_id": couple[0],
            "rank": rank,
            "user_a": {
                "user_id": couple[1],
                "username": couple[2],
                "mbti": couple[3],
                "profile_image_url": couple[4]
            },
            "user_b": {
                "user_id": couple[5],
                "username": couple[6],
                "mbti": couple[7],
                "profile_image_url": couple[8]
            },
            "score": float(couple[9]) if couple[9] is not None else 0.0,
            "couple_name": couple[10],
            "average_rating": average_rating,
            "rating_count": rating_count,
            "created_at": couple[11].isoformat() if couple[11] else None,
            "ratings_list": ratings_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("=" * 60)
        print("커플 상세 조회 오류:")
        print(traceback.format_exc())
        print("=" * 60)
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.put("/{couple_id}/rating")
def add_couple_rating(
    couple_id: int,
    rating_data: RatingCreate,
    connection = Depends(get_db)
):
    """커플 별점 등록"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_name = 'couple_ratings'
        """)
        
        if cursor.fetchone()[0] == 0:
            cursor.close()
            raise HTTPException(
                status_code=501, 
                detail="별점 기능을 사용하려면 couple_ratings 테이블을 먼저 생성해야 합니다."
            )
        
        cursor.execute("SELECT couple_id, score FROM couple_ranking WHERE couple_id = %s", (couple_id,))
        couple = cursor.fetchone()
        
        if not couple:
            cursor.close()
            raise HTTPException(status_code=404, detail="커플을 찾을 수 없습니다")
        
        if rating_data.rating < 1 or rating_data.rating > 5:
            cursor.close()
            raise HTTPException(status_code=400, detail="별점은 1~5 사이여야 합니다")
        
        cursor.execute("""
            INSERT INTO couple_ratings (couple_id, rating, comment, nickname)
            VALUES (%s, %s, %s, %s)
        """, (couple_id, rating_data.rating, rating_data.comment, rating_data.nickname))
        
        cursor.execute("""
            SELECT AVG(rating) FROM couple_ratings WHERE couple_id = %s
        """, (couple_id,))
        average_rating = cursor.fetchone()[0] or 0
        
        base_score = float(couple[1])
        rating_bonus = float(average_rating) * 4
        new_score = (base_score * 0.8) + rating_bonus
        
        cursor.execute("""
            UPDATE couple_ranking 
            SET score = %s
            WHERE couple_id = %s
        """, (new_score, couple_id))
        
        connection.commit()
        
        cursor.execute("""
            SELECT COUNT(*) + 1 FROM couple_ranking WHERE score > %s
        """, (new_score,))
        current_rank = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT cr.user_a_id, u1.username, cr.user_b_id, u2.username
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE cr.couple_id = %s
        """, (couple_id,))
        couple_info = cursor.fetchone()
        
        cursor.close()
        
        return {
            "success": True,
            "message": f"별점 {rating_data.rating}점이 반영되었습니다. 현재 평균: {average_rating:.2f}점",
            "submitted_rating": rating_data.rating,
            "submitted_comment": rating_data.comment,
            "couple": {
                "couple_id": couple_id,
                "user_a": {
                    "user_id": couple_info[0],
                    "username": couple_info[1]
                },
                "user_b": {
                    "user_id": couple_info[2],
                    "username": couple_info[3]
                },
                "average_rating": round(float(average_rating), 2),
                "score": round(float(new_score), 2),
                "rank": current_rank
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        import traceback
        print("=" * 60)
        print("별점 등록 오류:")
        print(traceback.format_exc())
        print("=" * 60)
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("")
def create_couple(couple: CoupleCreate, connection = Depends(get_db)):
    """커플 등록"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (couple.user_a_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="user_a를 찾을 수 없습니다")
        
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (couple.user_b_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="user_b를 찾을 수 없습니다")
        
        if couple.user_a_id == couple.user_b_id:
            cursor.close()
            raise HTTPException(status_code=400, detail="같은 사용자끼리 커플이 될 수 없습니다")
        
        cursor.execute("""
            SELECT couple_id FROM couple_ranking 
            WHERE (user_a_id = %s AND user_b_id = %s) 
               OR (user_a_id = %s AND user_b_id = %s)
        """, (couple.user_a_id, couple.user_b_id, couple.user_b_id, couple.user_a_id))
        
        if cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=400, detail="이미 커플로 등록되어 있습니다")
        
        cursor.execute("""
            SELECT mbti, heart_rate, temperature 
            FROM users WHERE user_id = %s
        """, (couple.user_a_id,))
        user_a = cursor.fetchone()
        
        cursor.execute("""
            SELECT mbti, heart_rate, temperature 
            FROM users WHERE user_id = %s
        """, (couple.user_b_id,))
        user_b = cursor.fetchone()
        
        from .compatibility import calculate_total_compatibility
        
        compatibility = calculate_total_compatibility(
            user_a[0], user_b[0],
            user_a[1] or 70, user_b[1] or 70,
            user_a[2] or 36.5, user_b[2] or 36.5
        )
        
        couple_name = couple.couple_name
        if not couple_name:
            cursor.execute("SELECT username FROM users WHERE user_id = %s", (couple.user_a_id,))
            username_a = cursor.fetchone()[0]
            cursor.execute("SELECT username FROM users WHERE user_id = %s", (couple.user_b_id,))
            username_b = cursor.fetchone()[0]
            couple_name = f"{username_a} ❤️ {username_b}"
        
        user_a_id = min(couple.user_a_id, couple.user_b_id)
        user_b_id = max(couple.user_a_id, couple.user_b_id)
        
        cursor.execute("""
            INSERT INTO couple_ranking (user_a_id, user_b_id, score, couple_name)
            VALUES (%s, %s, %s, %s)
        """, (user_a_id, user_b_id, compatibility['total_score'], couple_name))
        
        connection.commit()
        couple_id = cursor.lastrowid
        
        cursor.execute("""
            SELECT cr.couple_id, cr.user_a_id, u1.username as user_a_name,
                   u1.mbti as user_a_mbti, u1.profile_image_url as user_a_profile,
                   cr.user_b_id, u2.username as user_b_name,
                   u2.mbti as user_b_mbti, u2.profile_image_url as user_b_profile,
                   cr.score, cr.couple_name, cr.created_at
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE cr.couple_id = %s
        """, (couple_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return {
            "success": True,
            "message": "커플이 등록되었습니다",
            "couple": {
                "couple_id": result[0],
                "user_a": {
                    "user_id": result[1],
                    "username": result[2],
                    "mbti": result[3],
                    "profile_image_url": result[4]
                },
                "user_b": {
                    "user_id": result[5],
                    "username": result[6],
                    "mbti": result[7],
                    "profile_image_url": result[8]
                },
                "score": result[9],
                "couple_name": result[10],
                "created_at": result[11].isoformat() if result[11] else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")