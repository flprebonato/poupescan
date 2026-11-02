import hashlib
import logging
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from backend.app.database.session import get_db
from backend.app.api.dependencies import usuario_autenticado
from backend.app.schemas.despesa import DadosDespesa, DespesaAtualizacao, DespesaRequest, EstabelecimentoRequest, ItemRequest
from backend.app.database.models import Despesa, Estabelecimento, ItemDespesa, Produto, ProdutoEstabelecimento, Usuario
from backend.app.services.reader import MAX_IMAGE_BYTES, analisar_comprovante, validar_imagem
from backend.app.services.cadastro_cnpj import consultar_cnpj

router = APIRouter(prefix="/api", tags=["Despesas"])
logger = logging.getLogger(__name__)
MAX_DADOS_BYTES = 1024 * 1024


def validar_dados(esquema: type[DadosDespesa], bruto: str | bytes):
    try:
        return esquema.model_validate_json(bruto)
    except ValidationError as erro:
        erros = [{"campo": ".".join(str(p) for p in e["loc"]), "mensagem": e["msg"]} for e in erro.errors()]
        raise HTTPException(422, {"mensagem": "Revise os campos obrigatórios e os valores informados.", "campos": erros}) from None


async def ler_json(request: Request) -> bytes:
    bruto = bytearray()
    async for parte in request.stream():
        bruto += parte
        if len(bruto) > MAX_DADOS_BYTES:
            raise HTTPException(413, "Os dados enviados excedem o limite de 1 MB.")
    return bytes(bruto)


async def ler_envio(request: Request, *, com_dados: bool = False):
    async with request.form(max_files=1, max_fields=1 if com_dados else 0, max_part_size=MAX_DADOS_BYTES) as form:
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
            bruto = form.get("dados")
            if not isinstance(bruto, str):
                raise HTTPException(400, "O campo dados deve conter um JSON.")
            dados = validar_dados(DespesaRequest, bruto)
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


def resolver_estabelecimento(db: Session, usuario_id: int, dados: EstabelecimentoRequest) -> Estabelecimento:
    identidade = dados.cnpj or "|".join((dados.nome.casefold(), (dados.endereco or "").casefold()))
    identidade = hashlib.sha256(identidade.encode()).hexdigest()
    estabelecimento = db.scalar(select(Estabelecimento).where(
        Estabelecimento.usuario_id == usuario_id, Estabelecimento.identidade == identidade,
    ))
    if estabelecimento is None:
        estabelecimento = Estabelecimento(usuario_id=usuario_id, identidade=identidade, **dados.model_dump())
        db.add(estabelecimento)
    else:
        estabelecimento.nome = dados.nome
        estabelecimento.endereco = dados.endereco
    db.flush()
    return estabelecimento


def gravar(db: Session, usuario_id: int, dados: DadosDespesa, operacao, despesa_id: int | None = None):
    # A dependência de autenticação já iniciou a transação da sessão. Nenhum
    # cadastro auxiliar é confirmado antes de todos os itens serem gravados.
    for tentativa in range(3):
        try:
            resultado = operacao()
            db.commit()
            return resultado
        except IntegrityError:
            db.rollback()
            duplicada = select(Despesa.id).where(Despesa.usuario_id == usuario_id, Despesa.documento_chave == dados.documento_chave)
            if despesa_id is not None:
                duplicada = duplicada.where(Despesa.id != despesa_id)
            if dados.documento_chave and db.scalar(duplicada) is not None:
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


def persistir_despesa(db: Session, usuario_id: int, dados: DespesaRequest, conteudo: bytes, mime: str, nome: str):
    def operacao():
        estabelecimento = resolver_estabelecimento(db, usuario_id, dados.estabelecimento)
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
        return {"id": despesa.id, "mensagem": "Despesa cadastrada com sucesso!", "quantidade_itens": len(dados.itens)}
    return gravar(db, usuario_id, dados, operacao)


def confirmar_cadastro(dados: DadosDespesa):
    cadastro = consultar_cnpj(dados.estabelecimento.cnpj)
    if (
        cadastro.get("status") != "sucesso" or not cadastro.get("validado")
        or cadastro.get("cnpj") != dados.estabelecimento.cnpj or not cadastro.get("razao_social")
    ):
        mensagem = "Não foi possível confirmar o cadastro do CNPJ. Consulte novamente antes de salvar."
        status = 503 if cadastro.get("status") in {"indisponivel", "desativada"} else 422
        raise HTTPException(status, {"mensagem": mensagem, "campos": [{"campo": "estabelecimento.cnpj", "mensagem": mensagem}]})
    dados.estabelecimento.nome = cadastro["razao_social"]
    dados.estabelecimento.endereco = cadastro.get("endereco")


@router.post("/despesas", status_code=201)
async def cadastrar_despesa(request: Request, usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db)):
    conteudo, mime, nome, dados = await ler_envio(request, com_dados=True)
    await run_in_threadpool(confirmar_cadastro, dados)
    return await run_in_threadpool(persistir_despesa, db, usuario.id, dados, conteudo, mime, nome)


def despesa_do_usuario(db: Session, usuario_id: int, despesa_id: int) -> Despesa:
    despesa = db.scalar(select(Despesa).where(Despesa.id == despesa_id, Despesa.usuario_id == usuario_id))
    if despesa is None:
        raise HTTPException(404, "Despesa não encontrada.")
    return despesa


def resumo_despesa(despesa: Despesa):
    return {campo: getattr(despesa, campo) for campo in (
        "id", "data_despesa", "hora_despesa", "valor_total", "desconto_total", "valor_pago", "quantidade_itens",
        "forma_pagamento", "documento_tipo", "documento_chave", "qrcode_identificado", "arquivo_nome", "criado_em", "atualizado_em",
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


def corrigir_despesa(db: Session, usuario_id: int, despesa: Despesa, dados: DespesaAtualizacao):
    existentes, vistos = {item.id for item in despesa.itens}, set()
    for indice, item in enumerate(dados.itens):
        if item.id is None:
            continue
        if item.id not in existentes or item.id in vistos:
            mensagem = "Um dos itens não pertence mais a esta despesa. Recarregue a página e refaça a correção."
            raise HTTPException(422, {"mensagem": mensagem, "campos": [{"campo": f"itens.{indice}.id", "mensagem": mensagem}]})
        vistos.add(item.id)
    # Sem troca de CNPJ, o estabelecimento salvo é mantido e a consulta externa é dispensada.
    cnpj_alterado = dados.estabelecimento.cnpj != despesa.estabelecimento.cnpj
    if cnpj_alterado:
        confirmar_cadastro(dados)

    def operacao():
        estabelecimento = resolver_estabelecimento(db, usuario_id, dados.estabelecimento) if cnpj_alterado else despesa.estabelecimento
        for campo, valor in dados.model_dump(exclude={"estabelecimento", "itens"}).items():
            setattr(despesa, campo, valor)
        registros = {item.id: item for item in despesa.itens}
        itens = []
        for item in dados.itens:
            registro = registros.get(item.id)
            if registro is None:
                registro = ItemDespesa(
                    produto_id=resolver_produto(db, estabelecimento.id, item).id,
                    descricao_original=item.descricao_original or item.descricao,
                )
            # Itens sem código mantêm o próprio produto mesmo com outro estabelecimento.
            elif item.codigo != registro.codigo or (cnpj_alterado and item.codigo):
                registro.produto_id = resolver_produto(db, estabelecimento.id, item).id
            for campo, valor in item.model_dump(exclude={"id", "descricao_original"}).items():
                setattr(registro, campo, valor)
            itens.append(registro)
        despesa.estabelecimento = estabelecimento
        # Itens ausentes da lista corrigida são excluídos (delete-orphan).
        despesa.itens = itens
        despesa.quantidade_itens = len(itens)
        despesa.atualizado_em = func.now()
        return {"id": despesa.id, "mensagem": "Despesa atualizada com sucesso!", "quantidade_itens": len(itens)}
    return gravar(db, usuario_id, dados, operacao, despesa.id)


@router.put("/despesas/{despesa_id}")
async def atualizar_despesa(despesa_id: int, request: Request, usuario: Usuario = Depends(usuario_autenticado), db: Session = Depends(get_db)):
    despesa = await run_in_threadpool(despesa_do_usuario, db, usuario.id, despesa_id)
    dados = validar_dados(DespesaAtualizacao, await ler_json(request))
    return await run_in_threadpool(corrigir_despesa, db, usuario.id, despesa, dados)


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
