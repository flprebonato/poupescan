import hashlib
import os
import re

os.environ["DATABASE_URL"] = "sqlite+pysqlite://"
os.environ["AUTH_SECRET_KEY"] = "test-secret-key-with-enough-random-characters"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Usuario


test_engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)
Base.metadata.create_all(test_engine)


def override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db


def limpar_usuarios():
    with TestSession() as db:
        db.query(Usuario).delete()
        db.commit()


def com_captcha(client, dados):
    captcha = client.get("/api/auth/captcha").json()
    numeros = [int(numero) for numero in re.findall(r"\d+", captcha["pergunta"])]
    return {
        **dados,
        "captcha_token": captcha["token"],
        "captcha_resposta": sum(numeros),
    }


def test_cadastro_normaliza_email_e_nao_expoe_senha():
    limpar_usuarios()
    client = TestClient(app)

    response = client.post(
        "/api/auth/cadastro",
        json=com_captcha(
            client,
            {"nome": "  Maria   Silva  ", "email": "  Maria@Example.COM ", "senha": "senha-super-segura"},
        ),
    )

    assert response.status_code == 201
    assert response.json()["usuario"]["nome"] == "Maria Silva"
    assert response.json()["usuario"]["email"] == "maria@example.com"
    assert "senha" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]

    with TestSession() as db:
        usuario = db.scalar(select(Usuario))
        assert usuario.senha_hash != "senha-super-segura"
        assert usuario.senha_hash.startswith("$argon2")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "maria@example.com"


def test_cadastro_rejeita_email_duplicado_e_senha_curta():
    limpar_usuarios()
    client = TestClient(app)
    payload = {"nome": "Maria Silva", "email": "maria@example.com", "senha": "senha-super-segura"}
    assert client.post("/api/auth/cadastro", json=com_captcha(client, payload)).status_code == 201

    duplicate = client.post(
        "/api/auth/cadastro",
        json=com_captcha(client, {**payload, "email": "MARIA@example.com"}),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Este e-mail já está associado a uma conta."

    short_password = client.post(
        "/api/auth/cadastro",
        json=com_captcha(client, {"nome": "João", "email": "joao@example.com", "senha": "curta"}),
    )
    assert short_password.status_code == 422


def test_login_logout_e_credenciais_invalidas():
    limpar_usuarios()
    client = TestClient(app)
    client.post(
        "/api/auth/cadastro",
        json=com_captcha(
            client,
            {"nome": "Ana Souza", "email": "ana@example.com", "senha": "uma-senha-bem-segura"},
        ),
    )
    client.post("/api/auth/logout")

    invalid = client.post("/api/auth/login", json={"email": "ana@example.com", "senha": "senha-errada"})
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "E-mail ou senha inválidos."

    login = client.post(
        "/api/auth/login",
        json={"email": " ANA@EXAMPLE.COM ", "senha": "uma-senha-bem-segura"},
    )
    assert login.status_code == 200
    assert login.json()["usuario"]["nome"] == "Ana Souza"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_login_aceita_scrypt_legado_e_migra_para_argon2():
    limpar_usuarios()
    client = TestClient(app)
    senha = "senha-legada-segura"
    salt = bytes.fromhex("9279fd2357438d3e4564471029384756")
    resultado = hashlib.scrypt(senha.encode(), salt=salt, n=16384, r=8, p=1, dklen=64)

    with TestSession() as db:
        db.add(
            Usuario(
                nome="Usuário Legado",
                email="legado@example.com",
                senha_hash=f"scrypt$16384$8$1${salt.hex()}${resultado.hex()}",
            )
        )
        db.commit()

    response = client.post("/api/auth/login", json={"email": "legado@example.com", "senha": senha})

    assert response.status_code == 200
    with TestSession() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == "legado@example.com"))
        assert usuario.senha_hash.startswith("$argon2")


def test_usuario_pode_atualizar_nome_email_e_senha():
    limpar_usuarios()
    client = TestClient(app)
    client.post(
        "/api/auth/cadastro",
        json=com_captcha(
            client,
            {"nome": "Nome Antigo", "email": "antigo@example.com", "senha": "senha-antiga-segura"},
        ),
    )

    senha_incorreta = client.patch(
        "/api/auth/me",
        json={
            "nome": "Nome Novo",
            "email": "novo@example.com",
            "senha_atual": "senha-incorreta",
            "nova_senha": "senha-nova-segura",
        },
    )
    assert senha_incorreta.status_code == 400
    assert senha_incorreta.json()["detail"] == "A senha atual está incorreta."

    response = client.patch(
        "/api/auth/me",
        json={
            "nome": "  Nome   Novo  ",
            "email": " NOVO@EXAMPLE.COM ",
            "senha_atual": "senha-antiga-segura",
            "nova_senha": "senha-nova-segura",
        },
    )
    assert response.status_code == 200
    assert response.json()["usuario"]["nome"] == "Nome Novo"
    assert response.json()["usuario"]["email"] == "novo@example.com"

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login", json={"email": "novo@example.com", "senha": "senha-antiga-segura"}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": "novo@example.com", "senha": "senha-nova-segura"}
    ).status_code == 200


def test_tela_expoe_formulario_e_navegacao_de_cadastro():
    limpar_usuarios()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="register-form"' in response.text
    assert 'id="register-name"' in response.text
    assert 'id="register-email"' in response.text
    assert 'id="register-password"' in response.text
    assert 'id="captcha-answer"' in response.text
    assert 'id="show-register"' in response.text
    assert 'src="assets/logo-poupescan.png"' in response.text
    assert 'auth-tabs' not in response.text

    logo = client.get("/assets/logo-poupescan.png")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"


def test_area_autenticada_expoe_configuracoes_de_perfil():
    limpar_usuarios()
    client = TestClient(app)
    client.post(
        "/api/auth/cadastro",
        json=com_captcha(
            client,
            {"nome": "Maria Silva", "email": "maria@example.com", "senha": "senha-super-segura"},
        ),
    )

    response = client.get("/app")

    assert response.status_code == 200
    assert '<button class="account-button" id="settings-button" type="button">Minha Conta</button>' in response.text
    assert 'class="settings-button"' not in response.text
    assert 'id="settings-form"' in response.text
    assert 'name="nome"' in response.text
    assert 'name="email"' in response.text
    assert 'name="nova_senha"' in response.text


def test_cadastro_rejeita_captcha_incorreto():
    limpar_usuarios()
    client = TestClient(app)
    captcha = client.get("/api/auth/captcha").json()

    response = client.post(
        "/api/auth/cadastro",
        json={
            "nome": "Robô",
            "email": "robo@example.com",
            "senha": "senha-super-segura",
            "captcha_token": captcha["token"],
            "captcha_resposta": 100,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Resposta do CAPTCHA incorreta ou expirada."
