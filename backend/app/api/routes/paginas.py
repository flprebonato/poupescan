from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies import COOKIE_NAME
from backend.app.core.config import FRONTEND_DIR
from backend.app.core.security import decodificar_token
from backend.app.database.models import Usuario
from backend.app.database.session import get_db


router = APIRouter()


@router.get("/", include_in_schema=False)
def pagina_autenticacao(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    usuario_id = decodificar_token(token) if token else None
    if usuario_id is not None and db.get(Usuario, usuario_id) is not None:
        return RedirectResponse("/app", status_code=status.HTTP_302_FOUND)
    return FileResponse(FRONTEND_DIR / "index.html")


@router.get("/app", include_in_schema=False)
def pagina_autenticada(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    usuario_id = decodificar_token(token) if token else None
    if usuario_id is None or db.get(Usuario, usuario_id) is None:
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return FileResponse(FRONTEND_DIR / "central.html")
