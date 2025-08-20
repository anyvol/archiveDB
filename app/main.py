from fastapi import FastAPI, Security
import os

from app.database import engine
from app.models import Base
from app.routers import router as user_router
from app import docs

app = FastAPI()

app.include_router(user_router, prefix="/users")
app.include_router(docs.router, prefix="/docs")

@app.on_event("startup")
async def startup_event():
    # Создание таблиц
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Вывод переменных окружения для проверки
    print("DATABASE_URL:", os.getenv("DATABASE_URL"))
    print("SECRET_KEY:", os.getenv("SECRET_KEY"))
    print("ACCESS_TOKEN_MINUTES:", os.getenv("ACCESS_TOKEN_MINUTES"))
    print("ALGORITHM:", os.getenv("ALGORITHM"))

@app.get("/")
async def root():
    return {"message": "App is running"}

@app.get("/env")
async def get_env():
    return {
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "ACCESS_TOKEN_MINUTES": os.getenv("ACCESS_TOKEN_MINUTES"),
        "ALGORITHM": os.getenv("ALGORITHM"),
    }

