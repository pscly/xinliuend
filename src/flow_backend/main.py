from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flow_backend.config import settings
from flow_backend.routers import admin, auth, settings as settings_router, sync as sync_router, todo

app = FastAPI(title=settings.app_name)

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

origins = settings.cors_origins_list()
if origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(settings_router.router, prefix=settings.api_prefix)
app.include_router(todo.router, prefix=settings.api_prefix)
app.include_router(sync_router.router, prefix=settings.api_prefix)
app.include_router(admin.router)
