from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalizar_email(email: str) -> str:
    return email.strip().casefold()


class CadastroRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=10, max_length=128)
    captcha_token: str = Field(min_length=1)
    captcha_resposta: int = Field(ge=0, le=100)

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, nome: str) -> str:
        nome_normalizado = " ".join(nome.split())
        if len(nome_normalizado) < 2:
            raise ValueError("Informe seu nome.")
        return nome_normalizado

    @field_validator("email")
    @classmethod
    def validar_email(cls, email: EmailStr) -> str:
        return normalizar_email(str(email))


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validar_email(cls, email: EmailStr) -> str:
        return normalizar_email(str(email))


class AtualizarPerfilRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha_atual: str = Field(min_length=1, max_length=128)
    nova_senha: str | None = Field(default=None, min_length=10, max_length=128)

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, nome: str) -> str:
        nome_normalizado = " ".join(nome.split())
        if len(nome_normalizado) < 2:
            raise ValueError("Informe seu nome.")
        return nome_normalizado

    @field_validator("email")
    @classmethod
    def validar_email(cls, email: EmailStr) -> str:
        return normalizar_email(str(email))

    @field_validator("nova_senha", mode="before")
    @classmethod
    def normalizar_nova_senha(cls, senha: str | None) -> str | None:
        return senha or None


class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: EmailStr
    criado_em: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    mensagem: str
    usuario: UsuarioResponse


class MensagemResponse(BaseModel):
    mensagem: str


class CaptchaResponse(BaseModel):
    pergunta: str
    token: str
