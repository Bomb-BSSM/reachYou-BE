from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .APIRouter import users, compatibility, confessions, couples, fated_match

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users.router)
app.include_router(compatibility.router)
app.include_router(confessions.router)
app.include_router(couples.router)
app.include_router(fated_match.router)

@app.get("/")
def root():
    return {"message": "FastAPI 서버가 실행중입니다 (reach_you DB 연결)"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)