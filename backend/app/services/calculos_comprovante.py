"""Completa somente valores dedutíveis, preservando os valores lidos da imagem."""
from decimal import Decimal, ROUND_HALF_UP


CENTAVO = Decimal("0.01")
MAX_VALOR = Decimal("999999999999.99")
UNIDADES_FRACIONADAS = {"KG", "G", "GR", "L", "LT", "ML"}


def moeda(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def completar_valores(dados: dict) -> dict:
    calculados = []

    def numero(objeto, campo):
        valor = objeto.get(campo)
        if valor is None:
            return None
        valor = Decimal(str(valor))
        return valor if valor.is_finite() and 0 <= valor <= MAX_VALOR else None

    def preencher(objeto, campo, valor, prefixo=""):
        if objeto.get(campo) is None and valor is not None and 0 <= valor <= MAX_VALOR:
            objeto[campo] = float(moeda(valor))
            calculados.append(prefixo + campo)

    # Zero só é dedutível quando não há desconto geral ainda sem identificação.
    desconto_geral = numero(dados, "desconto_total")
    if desconto_geral is None and numero(dados, "valor_total") is not None and numero(dados, "valor_pago") is not None:
        desconto_geral = numero(dados, "valor_total") - numero(dados, "valor_pago")
    identificados = Decimal(0)
    for item in dados["itens"]:
        desconto = numero(item, "desconto")
        if desconto is not None:
            identificados += desconto
        else:
            quantidade, unitario, liquido = (numero(item, campo) for campo in ("quantidade", "preco_unitario", "preco_total"))
            if quantidade is not None and unitario is not None and liquido is not None and (item.get("unidade") or "").upper() not in UNIDADES_FRACIONADAS:
                identificados += max(Decimal(0), moeda(quantidade * unitario) - liquido)
    desconto_pendente = desconto_geral is not None and desconto_geral > identificados + CENTAVO
    brutos = []
    descontos = []
    coerentes = True
    for indice, item in enumerate(dados["itens"]):
        quantidade = numero(item, "quantidade")
        unitario = numero(item, "preco_unitario")
        if quantidade is None or quantidade <= 0 or unitario is None:
            coerentes = False
            continue
        bruto = moeda(quantidade * unitario)
        brutos.append(bruto)
        liquido = numero(item, "preco_total")
        desconto = numero(item, "desconto")
        prefixo = f"itens.{indice}."
        fracionado = (item.get("unidade") or "").upper() in UNIDADES_FRACIONADAS
        if liquido is not None:
            if fracionado and bruto != liquido and desconto is None:
                coerentes = False
            elif bruto != liquido or not desconto_pendente:
                preencher(item, "desconto", bruto - liquido, prefixo)
        elif desconto is not None:
            preencher(item, "preco_total", bruto - desconto, prefixo)
        desconto = numero(item, "desconto")
        liquido = numero(item, "preco_total")
        if desconto is not None:
            descontos.append(desconto)
        if (liquido is not None and liquido > bruto + CENTAVO) or (desconto is not None and desconto > bruto):
            coerentes = False
        if liquido is not None and desconto is not None and abs(bruto - desconto - liquido) > CENTAVO:
            coerentes = False

    if dados["itens"] and coerentes and len(brutos) == len(dados["itens"]):
        bruto_total = sum(brutos)
        preencher(dados, "valor_total", bruto_total)
        total = numero(dados, "valor_total")
        if total is not None and abs(total - bruto_total) <= CENTAVO:
            pago = numero(dados, "valor_pago")
            if pago is not None:
                preencher(dados, "desconto_total", total - pago)
            elif len(descontos) == len(dados["itens"]):
                preencher(dados, "desconto_total", sum(descontos))
            desconto_total = numero(dados, "desconto_total")
            if desconto_total is not None and desconto_total + CENTAVO >= sum(descontos):
                preencher(dados, "valor_pago", total - desconto_total)

    dados["campos_calculados"] = calculados
    return dados
