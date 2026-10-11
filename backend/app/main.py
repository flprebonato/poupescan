from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes.despesas import router as despesas_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.paginas import router as paginas_router
from backend.app.api.routes.usuarios import router as usuarios_router
from backend.app.core.config import FRONTEND_DIR, settings


app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.include_router(despesas_router)
app.include_router(usuarios_router)
app.include_router(health_router)
app.include_router(paginas_router)
