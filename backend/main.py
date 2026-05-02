from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.models.database import init_db

app = FastAPI(title="Sentinel AI System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/")
def root():
    return {"message": "Sentinel AI System is running"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "sentinel-ai-backend"}
