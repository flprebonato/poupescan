import hashlib
import logging
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from backend.app.database.session import get_db
from backend.app.api.dependencies import usuario_autenticado
from backend.app.schemas.despesa import DespesaRequest, ItemRequest
from backend.app.database.models import Despesa, Estabelecimento, ItemDespesa, Produto, ProdutoEstabelecimento, Usuario
from backend.app.services.reader import MAX_IMAGE_BYTES, analisar_comprovante, validar_imagem
from backend.app.services.cadastro_cnpj import consultar_cnpj

router = APIRouter(prefix="/api", tags=["Despesas"])
logger = logging.getLogger(__name__)


async def ler_envio(request: Request, *, com_dados: bool = False):
    async with request.form(max_files=1, max_fields=1 if com_dados else 0, max_part_size=1024 * 1024) as form:
        partes = form.multi_items()
        esperados = {"imagem", "dados"} if com_dados else {"imagem"}
        if len(partes) != len(esperados) or {k for k, _ in partes} != esperados:
            raise HTTPException(400, "Envie somente uma imagem no campo imagem" + (" e o JSON no campo dados." if com_dados else "."))
        arquivo = form.get("imagem")
        if not isinstance(arquivo, UploadFile):
            raise HTTPException(400, "Selecione a imagem do comprovante.")
        conteudo = await arquivo.read(MAX_IMAGE_BYTES + 1)
        mime = arquivo.content_type or ""
        await run_in_threadpool(validar_imagem, conteudo, mime)
        nome = PurePath((arquivo.filename or "comprovante").replace("\\", "/")).name[:255]
        dados = None
        if com_dados:
            try:
                bruto = form.get("dados")
                if not isinstance(bruto, str):
                    raise HTTPException(400, "O campo dados deve conter um JSON.")
                dados = DespesaRequest.model_validate_json(bruto)
            except ValidationError as erro:
                erros = [{"campo": ".".join(str(p) for p in e["loc"]), "mensagem": e["msg"]} for e in erro.errors()]
                raise HTTPException(422, {"mensagem": "Revise os campos obrigatórios e os valores informados.", "campos": erros}) from None
        return conteudo, mime, nome, dados


@router.post("/scan")
async def scan(request: Request, _: Usuario = Depends(usuario_autenticado)):
    conteudo, _, _, _ = await ler_envio(request)
    return await analisar_comprovante(conteudo)


@router.get("/estabelecimentos/cnpj/{cnpj}")
def consultar_estabelecimento(cnpj: str, _: Usuario = Depends(usuario_autenticado)):
    return consultar_cnpj(cnpj)


def resolver_produto(db: Session, estabelecimento_id: int, item: ItemRequest) -> Produto:
    vinculo = db.scalar(select(ProdutoEstabelecimento).where(
        ProdutoEstabelecimento.estabelecimento_id == estabelecimento_id,
        ProdutoEstabelecimento.codigo == item.codigo,
    )) if item.codigo else None
    produto = db.get(Produto, vinculo.produto_id) if vinculo else None
    if produto is None:
        produto = Produto(nome=item.descricao)
        db.add(produto)
        db.flush()
    if item.codigo:
        if vinculo:
            vinculo.produto_id = produto.id
        else:
            db.add(ProdutoEstabelecimento(estabelecimento_id=estabelecimento_id, produto_id=produto.id, codigo=item.codigo))
        db.flush()
    return produto


def persistir_despesa(db: Session, usuario_id: int, dados: DespesaRequest, conteudo: bytes, mime: str, nome: str):
    # A dependência de autenticação já iniciou a transação da sessão. Nenhum
    # cadastro auxiliar é confirmado antes de todos os itens serem gravados.
    for tentativa in range(3):
        try:
            identidade = dados.estabelecimento.cnpj or "|".join((
                dados.estabelecimento.nome.casefold(), (dados.estabelecimento.endereco or "").casefold(),
            ))
            identidade = hashlib.sha256(identidade.encode()).hexdigest()
            estabelecimento = db.scalar(select(Estabelecimento).where(
                Estabelecimento.usuario_id == usuario_id, Estabelecimento.identidade == identidade,
            ))
            if estabelecimento is None:
                estabelecimento = Estabelecimento(usuario_id=usuario_id, identidade=identidade, **dados.estabelecimento.model_dump())
                db.add(estabelecimento)
            else:
                estabelecimento.nome = dados.estabelecimento.nome
                estabelecimento.endereco = dados.estabelecimento.endereco
            db.flush()
            despesa = Despesa(
                usuario_id=usuario_id, estabelecimento_id=estabelecimento.id,
                quantidade_itens=len(dados.itens), arquivo_nome=nome, arquivo_mime=mime,
                arquivo_tamanho=len(conteudo), arquivo_dados=conteudo,
                **dados.model_dump(exclude={"estabelecimento", "itens"}),
            )
            db.add(despesa)
            db.flush()
            for item in dados.itens:
                produto = resolver_produto(db, estabelecimento.id, item)
                db.add(ItemDespesa(
                    despesa_id=despesa.id, produto_id=produto.id,
                    descricao_original=item.descricao_original or item.descricao,
                    **item.model_dump(exclude={"descricao_original"}),
                ))
            db.commit()
            return {"id": despesa.id, "mensagem": "Despesa cadastrada com sucesso!", "quantidade_itens": len(dados.itens)}
        except IntegrityError:
            db.rollback()
            if dados.documento_chave and db.scalar(select(Despesa.id).where(
                Despesa.usuario_id == usuario_id, Despesa.documento_chave == dados.documento_chave,
            )) is not None:
                raise HTTPException(409, "Este comprovante já está cadastrado na sua conta.") from None
            # Outra requisição pode ter criado o mesmo cadastro local.
            if tentativa == 2:
                raise HTTPException(409, "Houve um conflito ao salvar. Seus dados foram mantidos; tente novamente.") from None
        except HTTPException:
            db.rollback()
            raise
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Falha ao persistir despesa")
            raise HTTPException(503, "Não foi possível salvar a despesa. Seus dados foram mantidos; tente novamente.") from None


@router.post("/despesas", status_code=201)
async def cadastrar_despesa(request: Request, usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db)):
    conteudo, mime, nome, dados = await ler_envio(request, com_dados=True)
    cadastro = await run_in_threadpool(consultar_cnpj, dados.estabelecimento.cnpj)
    if (
        cadastro.get("status") != "sucesso" or not cadastro.get("validado")
        or cadastro.get("cnpj") != dados.estabelecimento.cnpj or not cadastro.get("razao_social")
    ):
        mensagem = "Não foi possível confirmar o cadastro do CNPJ. Consulte novamente antes de salvar."
        status = 503 if cadastro.get("status") in {"indisponivel", "desativada"} else 422
        raise HTTPException(status, {"mensagem": mensagem, "campos": [{"campo": "estabelecimento.cnpj", "mensagem": mensagem}]})
    dados.estabelecimento.nome = cadastro["razao_social"]
    dados.estabelecimento.endereco = cadastro.get("endereco")
    return await run_in_threadpool(persistir_despesa, db, usuario.id, dados, conteudo, mime, nome)


def despesa_do_usuario(db: Session, usuario_id: int, despesa_id: int) -> Despesa:
    despesa = db.scalar(select(Despesa).where(Despesa.id == despesa_id, Despesa.usuario_id == usuario_id))
    if despesa is None:
        raise HTTPException(404, "Despesa não encontrada.")
    return despesa


def resumo_despesa(despesa: Despesa):
    return {campo: getattr(despesa, campo) for campo in (
        "id", "data_despesa", "hora_despesa", "valor_total", "desconto_total", "valor_pago", "quantidade_itens",
        "forma_pagamento", "documento_tipo", "documento_chave", "qrcode_identificado", "arquivo_nome", "criado_em",
    )} | {"estabelecimento": {"nome": despesa.estabelecimento.nome, "cnpj": despesa.estabelecimento.cnpj, "endereco": despesa.estabelecimento.endereco}}


@router.get("/despesas")
def listar_despesas(usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db), limite: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    despesas = db.scalars(select(Despesa).options(selectinload(Despesa.estabelecimento)).where(
        Despesa.usuario_id == usuario.id,
    ).order_by(Despesa.data_despesa.desc(), Despesa.id.desc()).offset(offset).limit(limite + 1)).all()
    return {"despesas": [resumo_despesa(d) for d in despesas[:limite]], "tem_mais": len(despesas) > limite}


@router.get("/despesas/{despesa_id}")
def obter_despesa(despesa_id: int, usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db)):
    despesa = despesa_do_usuario(db, usuario.id, despesa_id)
    return resumo_despesa(despesa) | {"itens": [{campo: getattr(item, campo) for campo in (
        "id", "codigo", "descricao", "descricao_original", "apresentacao", "quantidade", "unidade", "preco_unitario", "desconto", "preco_total",
    )} for item in despesa.itens]}


@router.get("/despesas/{despesa_id}/imagem")
def obter_imagem(despesa_id: int, usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db)):
    despesa = despesa_do_usuario(db, usuario.id, despesa_id)
    return Response(content=despesa.arquivo_dados, media_type=despesa.arquivo_mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/despesas/{despesa_id}", status_code=204)
def excluir_despesa(despesa_id: int, usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db)):
    despesa = despesa_do_usuario(db, usuario.id, despesa_id)
    try:
        db.delete(despesa)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Não foi possível excluir a despesa. Tente novamente.") from None
    return Response(status_code=204)
