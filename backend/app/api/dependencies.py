from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database.session import get_db
from backend.app.database.models import Usuario
from backend.app.core.security import decodificar_token

COOKIE_NAME = "poupescan_session"


def usuario_autenticado(
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Usuario:
    usuario_id = decodificar_token(token) if token else None
    usuario = db.get(Usuario, usuario_id) if usuario_id is not None else None
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sua sessão é inválida ou expirou.")
    return usuario
