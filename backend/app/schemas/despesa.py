from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from backend.app.services.cadastro_cnpj import cnpj_valido
from backend.app.services.calculos_comprovante import CENTAVO, moeda

Dinheiro = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Preco = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4, allow_inf_nan=False)]
Quantidade = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=4, allow_inf_nan=False)]


class DadosBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def vazio_nulo(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class EstabelecimentoRequest(DadosBase):
    # Nome/endereço recebidos de clientes antigos são substituídos pelo cadastro.
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    cnpj: str
    endereco: str | None = Field(default=None, max_length=500)

    @field_validator("cnpj")
    @classmethod
    def validar_cnpj(cls, value):
        value = re.sub(r"[./\s-]", "", value)
        if not cnpj_valido(value) or not re.fullmatch(r"[0-9]{14}", value):
            raise ValueError("Informe um CNPJ válido para consultar o estabelecimento.")
        return value


class ItemRequest(DadosBase):
    codigo: str | None = Field(default=None, max_length=80)
    descricao: str = Field(min_length=1, max_length=500)
    descricao_original: str | None = Field(default=None, max_length=500)
    apresentacao: str | None = Field(default=None, max_length=100)
    quantidade: Quantidade
    unidade: str | None = Field(default=None, max_length=20)
    preco_unitario: Preco
    desconto: Dinheiro | None = None
    preco_total: Dinheiro | None = None

    @model_validator(mode="after")
    def validar_valores(self):
        bruto = moeda(self.quantidade * self.preco_unitario)
        if self.desconto is not None and self.desconto > bruto:
            raise ValueError("O desconto do item não pode superar quantidade × preço unitário.")
        if self.preco_total is not None:
            if self.preco_total > bruto + CENTAVO:
                raise ValueError("O total do item supera quantidade × preço unitário. Confira a leitura.")
            if self.desconto is not None and abs(bruto - self.desconto - self.preco_total) > CENTAVO:
                raise ValueError("O total do item deve ser quantidade × preço unitário menos o desconto.")
        return self


class DespesaRequest(DadosBase):
    estabelecimento: EstabelecimentoRequest
    data_despesa: date
    hora_despesa: time | None = None
    valor_total: Dinheiro
    desconto_total: Dinheiro | None = None
    valor_pago: Dinheiro | None = None
    forma_pagamento: str | None = Field(default=None, max_length=80)
    documento_tipo: str | None = Field(default=None, max_length=50)
    documento_chave: str | None = None
    qrcode_identificado: bool = False
    itens: list[ItemRequest] = Field(min_length=1, max_length=500)

    @field_validator("itens")
    @classmethod
    def validar_soma_itens(cls, itens, info: ValidationInfo):
        total = info.data.get("valor_total")
        if total is not None:
            soma = sum(moeda(item.quantidade * item.preco_unitario) for item in itens)
            # Mesma tolerância de um centavo utilizada na revisão do comprovante.
            if abs(soma - total) > Decimal("0.01"):
                raise ValueError(
                    "A soma dos itens difere do valor total. "
                    "Corrija os valores e os descontos antes de salvar."
                )
            desconto = info.data.get("desconto_total")
            pago = info.data.get("valor_pago")
            descontos_itens = Decimal(0)
            for item in itens:
                if item.desconto is not None:
                    descontos_itens += item.desconto
                elif item.preco_total is not None:
                    descontos_itens += max(Decimal(0), moeda(item.quantidade * item.preco_unitario) - item.preco_total)
            if desconto is not None:
                if desconto > total or desconto + CENTAVO < descontos_itens:
                    raise ValueError("Confira o desconto total: deve incluir os descontos dos itens e não superar o total.")
                if pago is not None and abs(total - desconto - pago) > CENTAVO:
                    raise ValueError("O valor a pagar deve ser o valor total menos o desconto total.")
        return itens

    @field_validator("documento_chave")
    @classmethod
    def normalizar_chave(cls, value):
        if value is None:
            return None
        value = re.sub(r"\s", "", value)
        return value or None


# A leitura aceita campos incompletos. As exigências só se aplicam ao salvar.
class ItemLido(BaseModel):
    codigo: str | None = None
    descricao: str | None = None
    apresentacao: str | None = None
    quantidade: float | None = None
    unidade: str | None = None
    preco_unitario: float | None = None
    desconto: float | None = None
    preco_total: float | None = None

class CabecalhoLido(BaseModel):
    estabelecimento: str | None = None
    cnpj: str | None = None
    endereco: str | None = None


def normalizar_data_lida(value):
    if not value or not isinstance(value, str):
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(value.strip(), formato).date().isoformat()
        except ValueError:
            continue
    return None


class ResumoLido(BaseModel):
    @field_validator("data_despesa", mode="before", check_fields=False)
    @classmethod
    def normalizar_data(cls, value):
        return normalizar_data_lida(value)

    data_despesa: str | None = None
    hora_despesa: str | None = None
    valor_total: float | None = None
    desconto_total: float | None = None
    valor_pago: float | None = None
    forma_pagamento: str | None = None
    documento_tipo: str | None = None
    documento_chave: str | None = None


class ComprovanteLido(CabecalhoLido, ResumoLido):
    itens: list[ItemLido] = Field(default_factory=list, max_length=500)


class ItensLidos(BaseModel):
    itens: list[ItemLido] = Field(default_factory=list, max_length=500)


class DescontoLido(BaseModel):
    codigo: str | None = None
    descricao: str | None = None
    desconto: float | None = None


class DescontosLidos(BaseModel):
    descontos: list[DescontoLido] = Field(default_factory=list, max_length=500)


class ChaveLida(BaseModel):
    documento_chave: str | None = None


class TotaisImpressos(BaseModel):
    rotulo_total_bruto: str | None = None
    data_despesa: str | None = None
    hora_despesa: str | None = None
    total_bruto_impresso: float | None = None
    desconto_total_impresso: float | None = None
    valor_a_pagar_impresso: float | None = None

    @field_validator("data_despesa", mode="before")
    @classmethod
    def normalizar_data(cls, value):
        return normalizar_data_lida(value)
