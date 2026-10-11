import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

CODIGOS_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}


def chave_acesso_valida(chave: str) -> bool:
    if len(chave) != 44 or not chave.isdigit() or chave[20:22] != "65":
        return False
    soma = sum(
        int(digito) * (2 + (indice % 8))
        for indice, digito in enumerate(reversed(chave[:-1]))
    )
    verificador = 11 - (soma % 11)
    if verificador >= 10:
        verificador = 0
    return verificador == int(chave[-1])


def extrair_chave_acesso(conteudo: str) -> str | None:
    decodificado = unquote(conteudo)
    consulta = parse_qs(urlparse(decodificado).query)
    candidatos = []
    for chave in ("p", "chNFe", "chnfe", "chave"):
        candidatos.extend(consulta.get(chave, []))
    candidatos.append(decodificado)
    for candidato in candidatos:
        encontrada = re.search(r"(?<!\d)(\d{44})(?!\d)", candidato)
        if encontrada and chave_acesso_valida(encontrada.group(1)):
            return encontrada.group(1)
    return None


def descrever_qrcode(conteudo: str) -> dict[str, Any] | None:
    chave = extrair_chave_acesso(conteudo)
    url = conteudo.strip()
    parsed = urlparse(url)
    if not chave or parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    return {
        "chave_acesso": chave,
        "uf": CODIGOS_UF.get(chave[:2]),
        "modelo": chave[20:22],
    }


def _decodificar(detector: Any, imagem: Any) -> list[str]:
    import cv2

    encontrados: list[str] = []
    try:
        ok, textos, _, _ = detector.detectAndDecodeMulti(imagem)
        if ok:
            encontrados.extend(texto.strip() for texto in textos if texto and texto.strip())
    except (cv2.error, ValueError):
        pass
    if not encontrados:
        try:
            texto, _, _ = detector.detectAndDecode(imagem)
            if texto and texto.strip():
                encontrados.append(texto.strip())
        except cv2.error:
            pass
    return encontrados


def ler_qrcodes(imagem: Any) -> list[dict[str, Any]]:
    """Detecta QR Codes e extrai chaves NFC-e sem acessar URLs da imagem."""
    import cv2

    detector = cv2.QRCodeDetector()
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(cinza)
    binaria = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 9
    )
    variantes = [imagem, cinza, clahe, binaria]
    # O detector pode falhar em módulos muito grandes mesmo com QR nítido.
    # Tenta outras escalas mantendo apenas pixels da imagem recebida.
    if min(imagem.shape[:2]) >= 400:
        variantes.extend(
            cv2.resize(cinza, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
            for escala in (0.5, 0.4)
        )
    conteudos: list[str] = []
    for variante in variantes:
        conteudos.extend(_decodificar(detector, variante))

    resultado: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for conteudo in conteudos:
        if conteudo in vistos:
            continue
        vistos.add(conteudo)
        descrito = descrever_qrcode(conteudo)
        if descrito:
            resultado.append(descrito)
        else:
            # Registra apenas a presença, sem inferir tipo fiscal ou expor URLs.
            resultado.append({"chave_acesso": None})
    return resultado
