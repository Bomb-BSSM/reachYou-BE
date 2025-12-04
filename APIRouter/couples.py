from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/couples", tags=["couples"])

class PostCreate(BaseModel):
    couple_id: int
    author_user_id: int
    title: str
    content: str

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class RatingUpdate(BaseModel):
    rating: int  # 1-5점

def get_db():
    from config import engine
    connection = engine.raw_connection()
    try:
        yield connection
    finally:
        connection.close()


def update_couple_ranking(connection):
    """모든 커플의 랭킹을 점수 기준으로 업데이트"""
    cursor = connection.cursor()
    
    # 점수 순으로 정렬
    cursor.execute("""
        SELECT couple_id, score
        FROM couple_ranking
        ORDER BY score DESC
    """)
    
    couples = cursor.fetchall()
    
    # 랭킹 업데이트
    for rank, couple in enumerate(couples, 1):
        cursor.execute("""
            UPDATE couple_ranking 
            SET rank = %s 
            WHERE couple_id = %s
        """, (rank, couple[0]))
    
    connection.commit()
    cursor.close()


@router.get("/ranking")
def get_couple_ranking(limit: int = 10, connection = Depends(get_db)):
    """커플 랭킹 조회 (별점 기준 정렬)"""
    try:
        # 랭킹 업데이트
        update_couple_ranking(connection)
        
        cursor = connection.cursor()
        
        # 상위 N개 커플 조회
        cursor.execute("""
            SELECT cr.couple_id, cr.user_a_id, u1.username as user_a_name, u1.mbti as user_a_mbti,
                   u1.profile_image_url as user_a_profile,
                   cr.user_b_id, u2.username as user_b_name, u2.mbti as user_b_mbti,
                   u2.profile_image_url as user_b_profile,
                   cr.score, cr.rank, cr.created_at
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            ORDER BY cr.rank ASC
            LIMIT %s
        """, (limit,))
        
        results = cursor.fetchall()
        
        ranking = []
        for row in results:
            couple_id = row[0]
            
            # 게시글 개수 조회
            cursor.execute("""
                SELECT COUNT(*) FROM couple_activities WHERE couple_id = %s
            """, (couple_id,))
            post_count = cursor.fetchone()[0]
            
            ranking.append({
                "couple_id": couple_id,
                "rank": row[10],
                "user_a": {
                    "user_id": row[1],
                    "username": row[2],
                    "mbti": row[3],
                    "profile_image_url": row[4]
                },
                "user_b": {
                    "user_id": row[5],
                    "username": row[6],
                    "mbti": row[7],
                    "profile_image_url": row[8]
                },
                "score": row[9],
                "post_count": post_count,
                "created_at": row[11].isoformat() if row[11] else None
            })
        
        cursor.close()
        
        return {
            "count": len(ranking),
            "ranking": ranking
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.put("/{couple_id}/rating")
def update_couple_rating(couple_id: int, rating: RatingUpdate, connection = Depends(get_db)):
    """커플 별점 업데이트 (1-5점)"""
    try:
        if rating.rating < 1 or rating.rating > 5:
            raise HTTPException(status_code=400, detail="별점은 1-5점 사이여야 합니다")
        
        cursor = connection.cursor()
        
        # 커플 존재 확인
        cursor.execute("SELECT couple_id FROM couple_ranking WHERE couple_id = %s", (couple_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="커플을 찾을 수 없습니다")
        
        # 별점을 100점 만점으로 환산 (1점=20, 2점=40, 3점=60, 4점=80, 5점=100)
        score = rating.rating * 20
        
        # 점수 업데이트
        cursor.execute("""
            UPDATE couple_ranking 
            SET score = %s 
            WHERE couple_id = %s
        """, (score, couple_id))
        
        connection.commit()
        
        # 랭킹 업데이트
        update_couple_ranking(connection)
        
        # 업데이트된 커플 정보 조회
        cursor.execute("""
            SELECT cr.couple_id, cr.user_a_id, u1.username as user_a_name,
                   cr.user_b_id, u2.username as user_b_name,
                   cr.score, cr.rank
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE cr.couple_id = %s
        """, (couple_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return {
            "success": True,
            "message": f"커플 별점이 {rating.rating}점으로 업데이트되었습니다",
            "couple": {
                "couple_id": result[0],
                "user_a": {
                    "user_id": result[1],
                    "username": result[2]
                },
                "user_b": {
                    "user_id": result[3],
                    "username": result[4]
                },
                "rating": rating.rating,
                "score": result[5],
                "rank": result[6]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/{couple_id}")
def get_couple_detail(couple_id: int, connection = Depends(get_db)):
    """커플 상세 정보 조회"""
    try:
        cursor = connection.cursor()
        
        # 커플 기본 정보
        cursor.execute("""
            SELECT cr.couple_id, cr.user_a_id, u1.username as user_a_name, u1.mbti as user_a_mbti,
                   u1.profile_image_url as user_a_profile,
                   cr.user_b_id, u2.username as user_b_name, u2.mbti as user_b_mbti,
                   u2.profile_image_url as user_b_profile,
                   cr.score, cr.rank, cr.created_at
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE cr.couple_id = %s
        """, (couple_id,))
        
        couple = cursor.fetchone()
        
        if not couple:
            cursor.close()
            raise HTTPException(status_code=404, detail="커플을 찾을 수 없습니다")
        
        # 게시글 개수
        cursor.execute("""
            SELECT COUNT(*) FROM couple_activities WHERE couple_id = %s
        """, (couple_id,))
        
        post_count = cursor.fetchone()[0]
        
        cursor.close()
        
        # 점수를 별점으로 환산 (100점=5점, 80점=4점, ...)
        rating = couple[9] // 20
        
        return {
            "couple_id": couple[0],
            "rank": couple[10],
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
            "score": couple[9],
            "rating": rating,
            "post_count": post_count,
            "created_at": couple[11].isoformat() if couple[11] else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/user/{user_id}")
def get_user_couple(user_id: int, connection = Depends(get_db)):
    """특정 사용자가 속한 커플 조회"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT cr.couple_id, cr.user_a_id, u1.username as user_a_name, u1.mbti as user_a_mbti,
                   u1.profile_image_url as user_a_profile,
                   cr.user_b_id, u2.username as user_b_name, u2.mbti as user_b_mbti,
                   u2.profile_image_url as user_b_profile,
                   cr.score, cr.rank, cr.created_at
            FROM couple_ranking cr
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE cr.user_a_id = %s OR cr.user_b_id = %s
        """, (user_id, user_id))
        
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="커플 정보를 찾을 수 없습니다")
        
        rating = result[9] // 20
        
        return {
            "couple_id": result[0],
            "rank": result[10],
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
            "rating": rating,
            "created_at": result[11].isoformat() if result[11] else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.post("/board")
def create_post(post: PostCreate, connection = Depends(get_db)):
    """커플 게시판 글 작성"""
    try:
        cursor = connection.cursor()
        
        # 커플 존재 확인
        cursor.execute("SELECT couple_id FROM couple_ranking WHERE couple_id = %s", (post.couple_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="커플을 찾을 수 없습니다")
        
        # 작성자가 해당 커플의 멤버인지 확인
        cursor.execute("""
            SELECT couple_id FROM couple_ranking 
            WHERE couple_id = %s AND (user_a_id = %s OR user_b_id = %s)
        """, (post.couple_id, post.author_user_id, post.author_user_id))
        
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=403, detail="이 커플의 멤버만 글을 작성할 수 있습니다")
        
        # 게시글 작성
        cursor.execute("""
            INSERT INTO couple_activities (couple_id, activity_type, content, points)
            VALUES (%s, %s, %s, %s)
        """, (post.couple_id, post.title, post.content, post.author_user_id))
        
        connection.commit()
        activity_id = cursor.lastrowid
        
        # 작성자 정보 조회
        cursor.execute("""
            SELECT username, profile_image_url FROM users WHERE user_id = %s
        """, (post.author_user_id,))
        author = cursor.fetchone()
        
        # 생성된 게시글 조회
        cursor.execute("""
            SELECT activity_id, couple_id, activity_type, content, points, created_at
            FROM couple_activities
            WHERE activity_id = %s
        """, (activity_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return {
            "success": True,
            "message": "게시글이 작성되었습니다",
            "post": {
                "post_id": result[0],
                "couple_id": result[1],
                "title": result[2],
                "content": result[3],
                "author": {
                    "user_id": post.author_user_id,
                    "username": author[0],
                    "profile_image_url": author[1]
                },
                "created_at": result[5].isoformat() if result[5] else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/board/all")
def get_all_posts(limit: int = 20, connection = Depends(get_db)):
    """전체 커플 게시판 글 목록 (최신순)"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT ca.activity_id, ca.couple_id, ca.activity_type as title, ca.content,
                   ca.points as author_user_id, ca.created_at,
                   u.username, u.profile_image_url,
                   u1.username as couple_a_name, u2.username as couple_b_name
            FROM couple_activities ca
            JOIN users u ON ca.points = u.user_id
            JOIN couple_ranking cr ON ca.couple_id = cr.couple_id
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            ORDER BY ca.created_at DESC
            LIMIT %s
        """, (limit,))
        
        results = cursor.fetchall()
        cursor.close()
        
        posts = [
            {
                "post_id": row[0],
                "couple_id": row[1],
                "title": row[2],
                "content": row[3],
                "author": {
                    "user_id": row[4],
                    "username": row[6],
                    "profile_image_url": row[7]
                },
                "couple_names": f"{row[8]} ❤️ {row[9]}",
                "created_at": row[5].isoformat() if row[5] else None
            }
            for row in results
        ]
        
        return {
            "count": len(posts),
            "posts": posts
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/board/couple/{couple_id}")
def get_couple_posts(couple_id: int, limit: int = 20, connection = Depends(get_db)):
    """특정 커플의 게시판 글 목록"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT ca.activity_id, ca.couple_id, ca.activity_type as title, ca.content,
                   ca.points as author_user_id, ca.created_at,
                   u.username, u.profile_image_url
            FROM couple_activities ca
            JOIN users u ON ca.points = u.user_id
            WHERE ca.couple_id = %s
            ORDER BY ca.created_at DESC
            LIMIT %s
        """, (couple_id, limit))
        
        results = cursor.fetchall()
        cursor.close()
        
        posts = [
            {
                "post_id": row[0],
                "couple_id": row[1],
                "title": row[2],
                "content": row[3],
                "author": {
                    "user_id": row[4],
                    "username": row[6],
                    "profile_image_url": row[7]
                },
                "created_at": row[5].isoformat() if row[5] else None
            }
            for row in results
        ]
        
        return {
            "couple_id": couple_id,
            "count": len(posts),
            "posts": posts
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.get("/board/{post_id}")
def get_post_detail(post_id: int, connection = Depends(get_db)):
    """게시글 상세 조회"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT ca.activity_id, ca.couple_id, ca.activity_type as title, ca.content,
                   ca.points as author_user_id, ca.created_at,
                   u.username, u.profile_image_url,
                   u1.username as couple_a_name, u2.username as couple_b_name,
                   cr.user_a_id, cr.user_b_id
            FROM couple_activities ca
            JOIN users u ON ca.points = u.user_id
            JOIN couple_ranking cr ON ca.couple_id = cr.couple_id
            JOIN users u1 ON cr.user_a_id = u1.user_id
            JOIN users u2 ON cr.user_b_id = u2.user_id
            WHERE ca.activity_id = %s
        """, (post_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다")
        
        return {
            "post_id": result[0],
            "couple_id": result[1],
            "title": result[2],
            "content": result[3],
            "author": {
                "user_id": result[4],
                "username": result[6],
                "profile_image_url": result[7]
            },
            "couple": {
                "user_a_name": result[8],
                "user_b_name": result[9],
                "couple_name": f"{result[8]} ❤️ {result[9]}"
            },
            "created_at": result[5].isoformat() if result[5] else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.put("/board/{post_id}")
def update_post(post_id: int, update: PostUpdate, connection = Depends(get_db)):
    """게시글 수정"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT activity_id FROM couple_activities WHERE activity_id = %s", (post_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다")
        
        update_fields = []
        update_values = []
        
        if update.title:
            update_fields.append("activity_type = %s")
            update_values.append(update.title)
        
        if update.content:
            update_fields.append("content = %s")
            update_values.append(update.content)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="수정할 내용이 없습니다")
        
        update_values.append(post_id)
        update_query = f"UPDATE couple_activities SET {', '.join(update_fields)} WHERE activity_id = %s"
        cursor.execute(update_query, tuple(update_values))
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": "게시글이 수정되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.delete("/board/{post_id}")
def delete_post(post_id: int, connection = Depends(get_db)):
    """게시글 삭제"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT activity_id FROM couple_activities WHERE activity_id = %s", (post_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다")
        
        cursor.execute("DELETE FROM couple_activities WHERE activity_id = %s", (post_id,))
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": "게시글이 삭제되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")


@router.delete("/{couple_id}")
def delete_couple(couple_id: int, connection = Depends(get_db)):
    """커플 삭제 (게시글도 함께 삭제)"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("SELECT couple_id FROM couple_ranking WHERE couple_id = %s", (couple_id,))
        if not cursor.fetchone():
            cursor.close()
            raise HTTPException(status_code=404, detail="커플을 찾을 수 없습니다")
        
        # 게시글 삭제
        cursor.execute("DELETE FROM couple_activities WHERE couple_id = %s", (couple_id,))
        
        # 커플 삭제
        cursor.execute("DELETE FROM couple_ranking WHERE couple_id = %s", (couple_id,))
        
        connection.commit()
        cursor.close()
        
        return {
            "success": True,
            "message": "커플이 삭제되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")