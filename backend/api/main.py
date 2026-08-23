"""App FastAPI del agente de reconciliacion de facturas."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

app = FastAPI(
    title="Agente de Reconciliacion de Facturas",
    description=(
        "Backend local-first. Toda la inferencia corre en el dispositivo; "
        "ningun dato de factura sale de la maquina."
    ),
    version="0.1.0",
)

# Streamlit, el frontend Vite y la aplicación Tauri consumen esta API local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
