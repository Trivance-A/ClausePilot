from fastapi import FastAPI

from app.api import chat, documents, guarantee_applications, regulations

app = FastAPI(title="AI 계약서 검증 및 규정 챗봇 시스템 API")

app.include_router(documents.router)
app.include_router(guarantee_applications.router)
app.include_router(regulations.router)
app.include_router(chat.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
