import json
from copy import deepcopy
import re
import time
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from backend.app.core.config import settings


CNPJ_LOOKUP_ENABLED = settings.cnpj_lookup_enabled
CNPJ_LOOKUP_URL = settings.cnpj_lookup_url.rstrip("/")
CNPJ_LOOKUP_TIMEOUT = max(1.0, settings.cnpj_lookup_timeout)
CNPJ_LOOKUP_SOURCE = "Minha Receita"
MAXIMO_RESPOSTA = 1024 * 1024

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = Lock()


def cnpj_valido(valor: str) -> bool:
    cnpj = re.sub(r"\D", "", str(valor or ""))
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False

    def digito(base: str, pesos: list[int]) -> str:
        soma = sum(int(numero) * peso for numero, peso in zip(base, pesos))
        resto = soma % 11
        return str(0 if resto < 2 else 11 - resto)

    primeiro = digito(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    segundo = digito(
        cnpj[:12] + primeiro,
        [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
    )
    return cnpj[-2:] == primeiro + segundo


def _texto(valor: Any) -> str | None:
    if not isinstance(valor, str):
        return None
    texto = re.sub(r"\s+", " ", valor).strip()
    return texto or None


def _formatar_cep(valor: Any) -> str | None:
    digitos = re.sub(r"\D", "", str(valor or ""))
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else None


def _campos_endereco(dados: dict[str, Any]) -> dict[str, str | None]:
    tipo = _texto(dados.get("descricao_tipo_de_logradouro"))
    logradouro = _texto(dados.get("logradouro"))
    primeira_parte = " ".join(parte for parte in (tipo, logradouro) if parte)
    return {
        "logradouro": primeira_parte or None,
        "numero": _texto(dados.get("numero")),
        "complemento": _texto(dados.get("complemento")),
        "bairro": _texto(dados.get("bairro")),
        "municipio": _texto(dados.get("municipio")),
        "uf": _texto(dados.get("uf")),
        "cep": _formatar_cep(dados.get("cep")),
    }


def _montar_endereco(dados: dict[str, Any]) -> str | None:
    campos = _campos_endereco(dados)
    partes = [campos[campo] for campo in ("logradouro", "numero", "complemento", "bairro", "municipio", "uf")]
    cep = campos["cep"]
    if cep:
        partes.append(f"CEP {cep}")
    endereco = ", ".join(parte for parte in partes if parte)
    return endereco or None


def _normalizar_resposta(dados: Any, cnpj_esperado: str) -> dict[str, Any]:
    if not isinstance(dados, dict):
        raise ValueError("A consulta cadastral não devolveu um objeto JSON.")
    cnpj_resposta = re.sub(r"\D", "", str(dados.get("cnpj") or ""))
    if cnpj_resposta != cnpj_esperado:
        raise ValueError("O cadastro devolveu um CNPJ diferente do consultado.")
    razao_social = _texto(dados.get("razao_social"))
    if not razao_social:
        raise ValueError("O cadastro não devolveu a razão social.")
    return {
        "status": "sucesso",
        "validado": True,
        "fonte": CNPJ_LOOKUP_SOURCE,
        "cnpj": cnpj_resposta,
        "razao_social": razao_social,
        "nome_fantasia": _texto(dados.get("nome_fantasia")),
        "situacao_cadastral": _texto(dados.get("descricao_situacao_cadastral")),
        "endereco": _montar_endereco(dados),
        "endereco_campos": _campos_endereco(dados),
    }


def _consultar_sem_cache(cnpj: str) -> dict[str, Any]:
    if not CNPJ_LOOKUP_ENABLED:
        return {"status": "desativada", "validado": False, "fonte": CNPJ_LOOKUP_SOURCE}
    parsed = urlparse(CNPJ_LOOKUP_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "status": "indisponivel",
            "validado": False,
            "fonte": CNPJ_LOOKUP_SOURCE,
            "mensagem": "A URL do serviço cadastral é inválida.",
        }
    requisicao = Request(
        f"{CNPJ_LOOKUP_URL}/{cnpj}",
        headers={"Accept": "application/json", "User-Agent": "PoupeScan/0.2"},
    )
    try:
        with urlopen(requisicao, timeout=CNPJ_LOOKUP_TIMEOUT) as resposta:
            conteudo = resposta.read(MAXIMO_RESPOSTA + 1)
        if len(conteudo) > MAXIMO_RESPOSTA:
            raise ValueError("A resposta cadastral excedeu o limite permitido.")
        return _normalizar_resposta(json.loads(conteudo), cnpj)
    except HTTPError as erro:
        status = "nao_encontrado" if erro.code == 404 else "indisponivel"
        return {
            "status": status,
            "validado": False,
            "fonte": CNPJ_LOOKUP_SOURCE,
            "mensagem": f"Consulta cadastral respondeu HTTP {erro.code}.",
        }
    except (URLError, OSError, ValueError) as erro:
        return {
            "status": "indisponivel",
            "validado": False,
            "fonte": CNPJ_LOOKUP_SOURCE,
            "mensagem": f"Consulta cadastral indisponível ({type(erro).__name__}).",
        }


def consultar_cnpj(valor: str | None) -> dict[str, Any]:
    cnpj = re.sub(r"\D", "", str(valor or ""))
    if not cnpj:
        return {
            "status": "nao_identificado",
            "validado": False,
            "fonte": CNPJ_LOOKUP_SOURCE,
        }
    if not cnpj_valido(cnpj):
        return {
            "status": "cnpj_invalido",
            "validado": False,
            "fonte": CNPJ_LOOKUP_SOURCE,
        }

    agora = time.monotonic()
    with _CACHE_LOCK:
        entrada = _CACHE.get(cnpj)
        if entrada and entrada[0] > agora:
            return deepcopy(entrada[1])

    resultado = _consultar_sem_cache(cnpj)
    # Falhas podem ser consultadas novamente assim que o serviço se recuperar.
    if resultado.get("status") == "sucesso":
        with _CACHE_LOCK:
            _CACHE[cnpj] = (agora + 24 * 60 * 60, deepcopy(resultado))
    return resultado


def aplicar_cadastro_ao_resumo(
    resumo: dict[str, Any], cadastro: dict[str, Any]
) -> None:
    if cadastro.get("status") != "sucesso" or not cadastro.get("validado"):
        return
    estabelecimento_lido = resumo.get("estabelecimento")
    endereco_lido = resumo.get("endereco")
    if estabelecimento_lido and estabelecimento_lido != cadastro["razao_social"]:
        resumo["estabelecimento_lido_imagem"] = estabelecimento_lido
    if endereco_lido and cadastro.get("endereco") and endereco_lido != cadastro["endereco"]:
        resumo["endereco_lido_imagem"] = endereco_lido
    resumo["cnpj"] = cadastro["cnpj"]
    resumo["estabelecimento"] = cadastro["razao_social"]
    if cadastro.get("nome_fantasia"):
        resumo["nome_fantasia"] = cadastro["nome_fantasia"]
    if cadastro.get("endereco"):
        resumo["endereco"] = cadastro["endereco"]
    if cadastro.get("situacao_cadastral"):
        resumo["situacao_cadastral"] = cadastro["situacao_cadastral"]
    resumo["fonte_estabelecimento"] = "cadastro_cnpj"
