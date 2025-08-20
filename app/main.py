from fastapi import FastAPI
from app.database import engine, async_session
from app.models import Base

app = FastAPI()

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def root():
    return {"message": "ArchiveDB API is running"}
