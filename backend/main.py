"""Unipage backend entry point -- FastAPI server.

Usage
-----
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

app = FastAPI(
    title="Unipage API",
    description="Backend for Unipage -- Unicode code chart file management and PDF generation.",
    version="2.0.0",
)

# Allow all origins during development (Svelte dev server on :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}
