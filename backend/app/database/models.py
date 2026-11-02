from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.session import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# Cadastros de estabelecimento pertencem ao usuário.
class Estabelecimento(Base):
    __tablename__ = "estabelecimentos"
    __table_args__ = (UniqueConstraint("usuario_id", "identidade", name="uq_estabelecimento_usuario"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    identidade: Mapped[str] = mapped_column(String(64))
    nome: Mapped[str] = mapped_column(String(255))
    cnpj: Mapped[str | None] = mapped_column(String(14))
    endereco: Mapped[str | None] = mapped_column(String(500))


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(500))


class ProdutoEstabelecimento(Base):
    __tablename__ = "produtos_estabelecimento"
    __table_args__ = (UniqueConstraint("estabelecimento_id", "codigo", name="uq_produto_codigo_local"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    estabelecimento_id: Mapped[int] = mapped_column(ForeignKey("estabelecimentos.id", ondelete="CASCADE"))
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"))
    codigo: Mapped[str] = mapped_column(String(80))


class Despesa(Base):
    __tablename__ = "despesas"
    __table_args__ = (
        UniqueConstraint("usuario_id", "documento_chave", name="uq_despesa_usuario_chave"),
        CheckConstraint("valor_total >= 0 AND (desconto_total IS NULL OR desconto_total >= 0) AND (valor_pago IS NULL OR valor_pago >= 0)", name="ck_despesa_valores"),
        CheckConstraint("quantidade_itens > 0", name="ck_despesa_itens"),
        CheckConstraint("arquivo_tamanho > 0 AND arquivo_tamanho <= 10485760", name="ck_despesa_arquivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    estabelecimento_id: Mapped[int] = mapped_column(ForeignKey("estabelecimentos.id"))
    data_despesa: Mapped[date] = mapped_column(Date, index=True)
    hora_despesa: Mapped[time | None] = mapped_column(Time)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    desconto_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    quantidade_itens: Mapped[int]
    forma_pagamento: Mapped[str | None] = mapped_column(String(80))
    documento_tipo: Mapped[str | None] = mapped_column(String(50))
    documento_chave: Mapped[str | None] = mapped_column(String(44))
    qrcode_identificado: Mapped[bool] = mapped_column(default=False)
    arquivo_nome: Mapped[str] = mapped_column(String(255))
    arquivo_mime: Mapped[str] = mapped_column(String(20))
    arquivo_tamanho: Mapped[int]
    arquivo_dados: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    estabelecimento: Mapped[Estabelecimento] = relationship()
    itens: Mapped[list["ItemDespesa"]] = relationship(cascade="all, delete-orphan", order_by="ItemDespesa.id")


class ItemDespesa(Base):
    __tablename__ = "itens_despesa"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_item_quantidade"),
        CheckConstraint("preco_unitario >= 0 AND (desconto IS NULL OR desconto >= 0) AND (preco_total IS NULL OR preco_total >= 0)", name="ck_item_valores"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    despesa_id: Mapped[int] = mapped_column(ForeignKey("despesas.id", ondelete="CASCADE"), index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"))
    codigo: Mapped[str | None] = mapped_column(String(80))
    descricao_original: Mapped[str] = mapped_column(String(500))
    descricao: Mapped[str] = mapped_column(String(500))
    apresentacao: Mapped[str | None] = mapped_column(String(100))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unidade: Mapped[str | None] = mapped_column(String(20))
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    desconto: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    preco_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    produto: Mapped[Produto] = relationship()
