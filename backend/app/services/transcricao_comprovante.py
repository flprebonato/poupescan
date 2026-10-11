"""Interpreta colunas literais sem pedir à IA que escolha desconto e total."""
from decimal import Decimal
import re

from backend.app.schemas.despesa import ItemRequest
from backend.app.services.calculos_comprovante import CENTAVO, moeda


NUMERO = r"(?:\d+|[1-9]\d{0,2}(?:\.\d{3})+)(?:,\d{1,4})?"
LINHA_PRODUTO = re.compile(
    rf"(?P<ordem>\d{{1,3}})\s+(?P<codigo>[A-Z0-9][A-Z0-9./-]*)\s+"
    rf"(?P<descricao>.+?)\s+(?P<quantidade_impressa>{NUMERO})\s*"
    rf"(?P<unidade>UND|UN|KG|GR|G|LT|L|ML|PC|PCT|CX)\s+"
    rf"(?P<preco_unitario_impresso>{NUMERO})\s+(?P<total_produto_impresso>{NUMERO})",
    re.I,
)


def numero_impresso(texto):
    if texto is None:
        raise ValueError("Coluna ilegível.")
    texto = re.sub(r"^R\$\s*", "", texto.strip())
    if not re.fullmatch(NUMERO, texto):
        raise ValueError("Número impresso ambíguo.")
    return Decimal(texto.replace(".", "").replace(",", "."))


def valores_desconto(linha):
    if not re.search(r"desconto", linha, re.I):
        raise ValueError("Linha sem identificação de desconto.")
    # Percentual não é dinheiro; conserva a ordem dos valores monetários.
    texto = re.sub(r"\d+(?:[.,]\d+)?\s*%", "", linha)
    valores = re.findall(r"(?<![\d.,])[-+]?\s*(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\d.,])", texto)
    numeros = [Decimal(re.sub(r"\s", "", valor).replace(".", "").replace(",", ".")) for valor in valores]
    if len(numeros) == 1:
        return abs(numeros[0]), None
    if len(numeros) == 2 and numeros[0] < 0 <= numeros[1]:
        return -numeros[0], numeros[1]
    raise ValueError("Não foi possível distinguir desconto e total líquido.")


def interpretar_itens_transcritos(itens):
    resultado = []
    for transcrito in itens:
        quantidade = numero_impresso(transcrito.get("quantidade_impressa"))
        unitario = numero_impresso(transcrito.get("preco_unitario_impresso"))
        total = numero_impresso(transcrito.get("total_produto_impresso"))
        bruto = moeda(quantidade * unitario)
        linha = transcrito.get("linha_desconto")
        desconto, liquido = valores_desconto(linha) if linha else (None, total)
        if desconto is None:
            # Uma quantidade incorreta não pode virar desconto por diferença.
            if abs(bruto - total) > CENTAVO:
                raise ValueError("Quantidade e colunas do produto não conferem.")
        elif abs(bruto - total) > CENTAVO and (liquido is None or abs(total - liquido) > CENTAVO):
            raise ValueError("Total do produto não confere com a linha de desconto.")
        item = {
            "codigo": transcrito.get("codigo"), "descricao": transcrito.get("descricao"),
            "apresentacao": transcrito.get("apresentacao"), "unidade": transcrito.get("unidade"),
            "quantidade": float(quantidade), "preco_unitario": float(unitario),
            "desconto": float(desconto) if desconto is not None else None,
            "preco_total": float(liquido) if liquido is not None else None,
        }
        ItemRequest.model_validate(item)
        resultado.append(item)
    return resultado


def interpretar_linhas_transcritas(linhas):
    """Associa desconto somente à linha anterior, com sequência e contas válidas.

    Formatos diferentes de tabela ficam para revisão; não adivinha colunas.
    """
    produtos = []
    pendente = ""
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if re.match(r"desconto\b", linha, re.I):
            if pendente or not produtos or produtos[-1].get("linha_desconto"):
                raise ValueError("Desconto sem um único produto imediatamente anterior.")
            produtos[-1]["linha_desconto"] = linha
            continue
        pendente = f"{pendente} {linha}".strip()
        correspondencia = LINHA_PRODUTO.fullmatch(pendente)
        if correspondencia:
            produto = correspondencia.groupdict()
            if int(produto.pop("ordem")) != len(produtos) + 1:
                raise ValueError("Produto ausente, repetido ou fora de ordem.")
            produtos.append(produto)
            pendente = ""
    if pendente:
        raise ValueError("Linha de produto incompleta ou formato não reconhecido.")
    return interpretar_itens_transcritos(produtos)
