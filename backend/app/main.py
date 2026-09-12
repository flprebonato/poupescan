from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models import Usuario
from backend.app.schemas import AtualizarPerfilRequest, AuthResponse, CadastroRequest, CaptchaResponse, LoginRequest, MensagemResponse, UsuarioResponse
from backend.app.security import criar_captcha, criar_token_acesso, decodificar_token, gerar_hash_senha, validar_captcha, verificar_e_atualizar_senha, verificar_senha


PROJECT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_DIR / "frontend"
COOKIE_NAME = "poupescan_session"


app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


def definir_cookie_autenticacao(response: Response, usuario_id: int) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=criar_token_acesso(usuario_id),
        max_age=settings.auth_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def usuario_autenticado(
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Usuario:
    usuario_id = decodificar_token(token) if token else None
    usuario = db.get(Usuario, usuario_id) if usuario_id is not None else None
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sua sessão é inválida ou expirou.",
        )
    return usuario


@app.post(
    "/api/auth/cadastro",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def cadastrar(dados: CadastroRequest, response: Response, db: Session = Depends(get_db)):
    if not validar_captcha(dados.captcha_token, dados.captcha_resposta):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resposta do CAPTCHA incorreta ou expirada.",
        )

    existente = db.scalar(select(Usuario.id).where(Usuario.email == dados.email))
    if existente is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este e-mail já está associado a uma conta.")

    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        senha_hash=gerar_hash_senha(dados.senha),
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já está associado a uma conta.",
        ) from None

    db.refresh(usuario)
    definir_cookie_autenticacao(response, usuario.id)
    return AuthResponse(mensagem="Conta criada com sucesso!", usuario=UsuarioResponse.model_validate(usuario))


@app.get("/api/auth/captcha", response_model=CaptchaResponse)
def obter_captcha():
    pergunta, token = criar_captcha()
    return CaptchaResponse(pergunta=pergunta, token=token)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(dados: LoginRequest, response: Response, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == dados.email))
    senha_valida, hash_atualizado = verificar_e_atualizar_senha(dados.senha, usuario.senha_hash) if usuario else (False, None)
    if not senha_valida:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )

    if hash_atualizado is not None:
        usuario.senha_hash = hash_atualizado
        db.commit()

    definir_cookie_autenticacao(response, usuario.id)
    return AuthResponse(mensagem="Login realizado com sucesso!", usuario=UsuarioResponse.model_validate(usuario))


@app.get("/api/auth/me", response_model=UsuarioResponse)
def obter_usuario_atual(usuario: Usuario = Depends(usuario_autenticado)):
    return usuario


@app.patch("/api/auth/me", response_model=AuthResponse)
def atualizar_perfil(
    dados: AtualizarPerfilRequest,
    usuario: Usuario = Depends(usuario_autenticado),
    db: Session = Depends(get_db),
):
    if not verificar_senha(dados.senha_atual, usuario.senha_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A senha atual está incorreta.")

    email_em_uso = db.scalar(
        select(Usuario.id).where(Usuario.email == dados.email, Usuario.id != usuario.id)
    )
    if email_em_uso is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este e-mail já está associado a uma conta.")

    usuario.nome = dados.nome
    usuario.email = dados.email
    if dados.nova_senha is not None:
        usuario.senha_hash = gerar_hash_senha(dados.nova_senha)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já está associado a uma conta.",
        ) from None

    db.refresh(usuario)
    return AuthResponse(
        mensagem="Dados atualizados com sucesso!",
        usuario=UsuarioResponse.model_validate(usuario),
    )


@app.post("/api/auth/logout", response_model=MensagemResponse)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.cookie_secure, samesite="lax")
    return MensagemResponse(mensagem="Sessão encerrada.")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def pagina_autenticacao(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    usuario_id = decodificar_token(token) if token else None
    if usuario_id is not None and db.get(Usuario, usuario_id) is not None:
        return RedirectResponse("/app", status_code=status.HTTP_302_FOUND)
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/app", include_in_schema=False)
def pagina_autenticada(_: Usuario = Depends(usuario_autenticado)):
    return FileResponse(FRONTEND_DIR / "dashboard.html")
