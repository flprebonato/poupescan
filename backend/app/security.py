from datetime import UTC, datetime, timedelta
import hashlib
import hmac
from secrets import randbelow
from typing import Any

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from backend.app.config import settings


ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


def gerar_hash_senha(senha: str) -> str:
    return password_hash.hash(senha)


def _verificar_scrypt_legado(senha: str, senha_hash: str) -> bool:
    try:
        algoritmo, n_texto, r_texto, p_texto, salt_texto, resultado_texto = senha_hash.split("$")
        n, r, p = int(n_texto), int(r_texto), int(p_texto)
        salt = bytes.fromhex(salt_texto)
        resultado_esperado = bytes.fromhex(resultado_texto)
    except (TypeError, ValueError):
        return False

    if (
        algoritmo != "scrypt"
        or n < 2**14
        or n > 2**20
        or n & (n - 1)
        or not 1 <= r <= 32
        or not 1 <= p <= 16
        or not 16 <= len(resultado_esperado) <= 128
    ):
        return False

    try:
        resultado = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(resultado_esperado),
        )
    except (ValueError, MemoryError):
        return False

    return hmac.compare_digest(resultado, resultado_esperado)


def verificar_e_atualizar_senha(senha: str, senha_hash: str) -> tuple[bool, str | None]:
    if senha_hash.startswith("scrypt$"):
        valido = _verificar_scrypt_legado(senha, senha_hash)
        return valido, gerar_hash_senha(senha) if valido else None

    try:
        return password_hash.verify_and_update(senha, senha_hash)
    except (UnknownHashError, TypeError, ValueError):
        return False, None


def verificar_senha(senha: str, senha_hash: str) -> bool:
    valido, _ = verificar_e_atualizar_senha(senha, senha_hash)
    return valido


def criar_token_acesso(usuario_id: int) -> str:
    agora = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.auth_token_minutes),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def decodificar_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def criar_captcha() -> tuple[str, str]:
    primeiro_numero = randbelow(9) + 1
    segundo_numero = randbelow(9) + 1
    agora = datetime.now(UTC)
    token = jwt.encode(
        {
            "tipo": "captcha",
            "resposta": primeiro_numero + segundo_numero,
            "iat": agora,
            "exp": agora + timedelta(minutes=5),
        },
        settings.auth_secret_key,
        algorithm=ALGORITHM,
    )
    return f"Quanto é {primeiro_numero} + {segundo_numero}?", token


def validar_captcha(token: str, resposta: int) -> bool:
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=[ALGORITHM])
        return payload.get("tipo") == "captcha" and payload.get("resposta") == resposta
    except InvalidTokenError:
        return False
