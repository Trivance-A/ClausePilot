from fastapi import FastAPI

from app.api import admin, auth, chat, documents, eval, extractions, guarantee, highlights, regulations, risks, search

app = FastAPI(title="ClausePilot API")

API_PREFIX = "/api/v1"

for router in (
    auth.router,
    documents.router,
    extractions.router,
    highlights.router,
    risks.router,
    guarantee.router,
    regulations.router,
    search.router,
    chat.router,
    admin.router,
    eval.router,
):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/health")
def health_check():
    return {"status": "ok"}
