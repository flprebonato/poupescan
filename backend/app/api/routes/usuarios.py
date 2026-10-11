from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.database.session import get_db
from backend.app.api.dependencies import COOKIE_NAME, usuario_autenticado
from backend.app.database.models import Usuario
from backend.app.core.security import (
    criar_captcha,
    criar_token_acesso,
    gerar_hash_senha,
    validar_captcha,
    verificar_e_atualizar_senha,
    verificar_senha,
)
from backend.app.schemas.usuario import (
    AtualizarPerfilRequest,
    AuthResponse,
    CadastroRequest,
    CaptchaResponse,
    LoginRequest,
    MensagemResponse,
    UsuarioResponse,
)


router = APIRouter(prefix="/api/auth", tags=["Usuários"])


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


@router.post(
    "/cadastro",
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


@router.get("/captcha", response_model=CaptchaResponse)
def obter_captcha():
    pergunta, token = criar_captcha()
    return CaptchaResponse(pergunta=pergunta, token=token)


@router.post("/login", response_model=AuthResponse)
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


@router.get("/me", response_model=UsuarioResponse)
def obter_usuario_atual(usuario: Usuario = Depends(usuario_autenticado)):
    return usuario


@router.patch("/me", response_model=AuthResponse)
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
        mensagem="Dados atualizados com sucesso.",
        usuario=UsuarioResponse.model_validate(usuario),
    )


@router.post("/logout", response_model=MensagemResponse)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.cookie_secure, samesite="lax")
    return MensagemResponse(mensagem="Sessão encerrada.")
