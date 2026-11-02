import asyncio
from copy import deepcopy
from io import BytesIO
import json
import os

os.environ['DATABASE_URL'] = 'sqlite+pysqlite://'
os.environ['AUTH_SECRET_KEY'] = 'test-secret-key-with-enough-random-characters'

import httpx
from PIL import Image
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import despesas
from backend.app.database.session import Base, get_db
from backend.app.main import app
from backend.app.database.models import Despesa, Estabelecimento, ItemDespesa, Produto, ProdutoEstabelecimento, Usuario
from backend.app.core.security import criar_token_acesso
from backend.app.services import reader


@pytest.fixture
def setup(monkeypatch):
    def cadastro(cnpj):
        return {
            'status': 'sucesso', 'validado': True, 'cnpj': cnpj,
            'razao_social': 'Mercado Teste', 'endereco': 'Rua A, 1',
            'endereco_campos': {'logradouro': 'Rua A', 'numero': '1'},
        }
    monkeypatch.setattr(despesas, 'consultar_cnpj', cadastro)
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with sessions() as db:
        db.add_all([Usuario(id=i, nome=f'Usuário {i}', email=f'user{i}@example.com', senha_hash='unused') for i in (1, 2)])
        db.commit()
    def override():
        with sessions() as db:
            yield db
    anterior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        client.cookies.set('poupescan_session', criar_token_acesso(1))
        yield client, sessions
    if anterior:
        app.dependency_overrides[get_db] = anterior
    else:
        app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.fixture
def imagem():
    buffer = BytesIO()
    Image.new('RGB', (60, 100), 'white').save(buffer, 'PNG')
    return buffer.getvalue()


@pytest.fixture
def dados():
    return {
        'estabelecimento': {'nome': 'Mercado Teste', 'cnpj': '11.222.333/0001-81', 'endereco': 'Rua A, 1'},
        'data_despesa': '2026-10-04', 'valor_total': '10.00', 'documento_chave': '1' * 44,
        'itens': [{'codigo': '001', 'descricao': 'Leite integral', 'descricao_original': 'LEITE INT', 'quantidade': '2', 'preco_unitario': '5.00', 'preco_total': '10.00'}],
    }


def salvar(client, dados, imagem):
    return client.post('/api/despesas', data={'dados': json.dumps(dados)}, files={'imagem': ('comprovante.png', imagem, 'image/png')})


def contagem(sessions, modelo):
    with sessions() as db:
        return db.scalar(select(func.count()).select_from(modelo))


def test_salvamento_consulta_imagem_exclusao_e_original(setup, imagem, dados):
    client, sessions = setup
    response = salvar(client, dados, imagem)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {'id', 'mensagem', 'quantidade_itens'}
    id = response.json()['id']
    detail = client.get(f'/api/despesas/{id}').json()
    assert detail['hora_despesa'] is None
    assert detail['desconto_total'] is None
    assert detail['valor_pago'] is None
    assert detail['itens'][0]['descricao_original'] == 'LEITE INT'
    assert detail['itens'][0]['descricao'] == 'Leite integral'
    assert len(client.get('/api/despesas').json()['despesas']) == 1
    receipt = client.get(f'/api/despesas/{id}/imagem')
    assert receipt.content == imagem
    assert receipt.headers['cache-control'] == 'private, no-store'
    assert client.delete(f'/api/despesas/{id}').status_code == 204
    assert contagem(sessions, Despesa) == contagem(sessions, ItemDespesa) == 0
    assert client.get(f'/api/despesas/{id}/imagem').status_code == 404


def test_chave_unica_por_usuario_e_isolamento(setup, imagem, dados):
    client, sessions = setup
    id = salvar(client, dados, imagem).json()['id']
    formatted = deepcopy(dados)
    formatted['documento_chave'] = ' '.join(['1111'] * 11)
    assert salvar(client, formatted, imagem).status_code == 409
    assert contagem(sessions, Despesa) == 1
    client.cookies.set('poupescan_session', criar_token_acesso(2))
    assert client.get('/api/despesas').json()['despesas'] == []
    assert client.get(f'/api/despesas/{id}').status_code == 404
    assert client.get(f'/api/despesas/{id}/imagem').status_code == 404
    assert client.delete(f'/api/despesas/{id}').status_code == 404
    dados['estabelecimento']['nome'] = 'Nome do segundo usuário'
    assert salvar(client, dados, imagem).status_code == 201
    client.cookies.set('poupescan_session', criar_token_acesso(1))
    assert client.get(f'/api/despesas/{id}').json()['estabelecimento']['nome'] == 'Mercado Teste'


@pytest.mark.parametrize('path,method', [('/api/scan','post'),('/api/estabelecimentos/cnpj/11222333000181','get'),('/api/despesas','post'),('/api/despesas','get'),('/api/despesas/1','get'),('/api/despesas/1','put'),('/api/despesas/1/imagem','get'),('/api/despesas/1','delete')])
def test_exige_sessao(setup, path, method):
    client, _ = setup
    client.cookies.clear()
    assert getattr(client, method)(path).status_code == 401
    assert client.get('/app', follow_redirects=False).headers['location'] == '/'


@pytest.mark.parametrize('campo,valor', [('estabelecimento', {'nome': '   '}), ('data_despesa', ''), ('data_despesa','2026-02-30'), ('valor_total',None), ('valor_total',-1), ('valor_total','NaN'), ('valor_total','Infinity'), ('valor_total','1000000000000'), ('desconto_total',-1), ('valor_pago',-1), ('itens',[])])
def test_validacao_despesa_sem_gravacao(setup, imagem, dados, campo, valor):
    client, sessions = setup
    dados[campo] = valor
    assert salvar(client, dados, imagem).status_code == 422
    assert contagem(sessions, Despesa) == contagem(sessions, Estabelecimento) == 0


@pytest.mark.parametrize('campo,valor', [('descricao',' '), ('quantidade',0), ('quantidade',-1), ('quantidade',None), ('preco_unitario',None), ('preco_unitario',-1), ('preco_total',-1), ('desconto',-1)])
def test_validacao_itens(setup, imagem, dados, campo, valor):
    client, sessions = setup
    dados['itens'][0][campo] = valor
    assert salvar(client, dados, imagem).status_code == 422
    assert contagem(sessions, Produto) == contagem(sessions, Despesa) == 0


@pytest.mark.parametrize('total', ['80.00', '194.96', '195.00'])
@pytest.mark.parametrize('total_explicito', [True, False])
def test_rejeita_soma_divergente_sem_gravar(setup, imagem, dados, total, total_explicito):
    client, sessions = setup
    dados['valor_total'] = total
    dados['itens'][0].update(quantidade='2', preco_unitario='97.49', preco_total='194.98')
    if not total_explicito:
        dados['itens'][0].pop('preco_total')
    response = salvar(client, dados, imagem)
    assert response.status_code == 422
    assert any(
        erro['campo'] == 'itens' and 'A soma dos itens difere' in erro['mensagem']
        for erro in response.json()['detail']['campos']
    )
    for modelo in (Despesa, ItemDespesa, Estabelecimento, Produto, ProdutoEstabelecimento):
        assert contagem(sessions, modelo) == 0
    dados['valor_total'] = '194.98'
    assert salvar(client, dados, imagem).status_code == 201


@pytest.mark.parametrize('total', ['0.29', '0.30', '0.31'])
def test_soma_decimal_com_tolerancia_de_um_centavo(setup, imagem, dados, total):
    client, _ = setup
    dados['valor_total'] = total
    dados['itens'] = [
        {'descricao': 'Item A', 'quantidade': '1', 'preco_unitario': '0.10'},
        {'descricao': 'Item B', 'quantidade': '1', 'preco_unitario': '0.20'},
    ]
    assert salvar(client, dados, imagem).status_code == 201


def test_nao_preenche_valores_opcionais_ausentes(setup, imagem, dados):
    client, _ = setup
    dados.pop('documento_chave')
    dados['itens'][0].pop('preco_total')
    for _ in range(2):
        response = salvar(client, dados, imagem)
        assert response.status_code == 201
        detail = client.get(f"/api/despesas/{response.json()['id']}").json()
        assert detail['itens'][0]['preco_total'] is None
        assert detail['itens'][0]['desconto'] is None


@pytest.mark.parametrize('nome,mime,conteudo,status', [('a.gif','image/gif',b'GIF89a',415), ('a.png','image/png',b'',400), ('a.png','image/png',b'not an image',400), ('a.jpg','image/jpeg',None,415), ('a.png','image/png',b'x'*(10*1024*1024+1),413)])
def test_validacao_imagem_scan_e_salvamento(setup, imagem, dados, nome, mime, conteudo, status):
    client, _ = setup
    conteudo = imagem if conteudo is None else conteudo
    for path in ('/api/scan', '/api/despesas'):
        response = client.post(path, files={'imagem': (nome, conteudo, mime)}, data={'dados': json.dumps(dados)} if path.endswith('despesas') else {})
        assert response.status_code == status, response.text


def test_rejeita_multiplas_imagens_e_json_invalido(setup, imagem):
    client, _ = setup
    files = [('imagem', ('a.png', imagem, 'image/png')), ('imagem', ('b.png', imagem, 'image/png'))]
    assert client.post('/api/scan', files=files).status_code == 400
    assert client.post('/api/despesas', files=files, data={'dados':'{}'}).status_code == 400
    assert client.post('/api/despesas', files={'imagem':('a.png',imagem,'image/png')}, data={'dados':'not json'}).status_code == 422


def test_scan_nao_persiste_nada_e_permite_retentativa(setup, imagem, monkeypatch):
    client, sessions = setup
    async def ler(_):
        return {'estabelecimento': 'Mercado', 'valor_total': None, 'itens': []}
    monkeypatch.setattr(despesas, 'analisar_comprovante', ler)
    response = client.post('/api/scan', files={'imagem': ('a.png', imagem, 'image/png')})
    assert response.status_code == 200
    assert response.json()['valor_total'] is None
    assert contagem(sessions, Despesa) == contagem(sessions, Produto) == 0
    async def falhar(_):
        raise HTTPException(503, 'Leitura indisponível')
    monkeypatch.setattr(despesas, 'analisar_comprovante', falhar)
    assert client.post('/api/scan', files={'imagem': ('a.png', imagem, 'image/png')}).status_code == 503


def test_codigo_local_reutiliza_produto_apenas_no_mesmo_estabelecimento(setup, imagem, dados):
    client, sessions = setup
    dados.pop('documento_chave')
    primeiro = salvar(client, dados, imagem).json()['id']
    dados['estabelecimento'] = {'cnpj': '93209765067025'}
    segundo = salvar(client, dados, imagem).json()['id']
    with sessions() as db:
        ids = [db.scalar(select(ItemDespesa.produto_id).where(ItemDespesa.despesa_id == id)) for id in (primeiro, segundo)]
        assert ids[0] != ids[1]
    terceiro = salvar(client, dados, imagem).json()['id']
    with sessions() as db:
        ids = [db.scalar(select(ItemDespesa.produto_id).where(ItemDespesa.despesa_id == id)) for id in (segundo, terceiro)]
        assert ids[0] == ids[1]


def test_rollback_inclui_cadastros_e_itens_anteriores(setup, imagem, dados, monkeypatch):
    client, sessions = setup
    dados['itens'].append({**dados['itens'][0], 'codigo':'002'})
    dados['valor_total'] = '20.00'
    original = despesas.resolver_produto
    def falhar_no_segundo(db, estabelecimento_id, item):
        if item.codigo == '002':
            raise SQLAlchemyError('Falha simulada no segundo item')
        return original(db, estabelecimento_id, item)
    monkeypatch.setattr(despesas, 'resolver_produto', falhar_no_segundo)
    assert salvar(client, dados, imagem).status_code == 503
    for model in (Despesa, ItemDespesa, Estabelecimento, Produto, ProdutoEstabelecimento):
        assert contagem(sessions, model) == 0
    monkeypatch.setattr(despesas, 'resolver_produto', original)
    assert salvar(client, dados, imagem).status_code == 201


def test_item_sem_codigo_nao_unifica_produtos_pela_descricao(setup, imagem, dados):
    client, sessions = setup
    dados.pop('documento_chave')
    dados['itens'][0].pop('codigo')
    assert salvar(client, dados, imagem).status_code == 201
    assert salvar(client, dados, imagem).status_code == 201
    assert contagem(sessions, Produto) == contagem(sessions, Despesa) == 2


@pytest.mark.parametrize('resposta,status', [({'message':{'content':'not json'}},502), ({'message':{'content':'{}'}},502), ({'error':'unavailable'},503)])
def test_falhas_ollama(imagem, monkeypatch, resposta, status):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(503 if status == 503 else 200, json=resposta))
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(HTTPException) as error:
        asyncio.run(reader.analisar_comprovante(imagem))
    assert error.value.status_code == status


def test_leitura_ollama_sem_inventar_dados(imagem, monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        body = json.loads(request.content)
        assert body['messages'][0]['images']
        assert body['format']['type'] == 'object'
        return httpx.Response(200, json={'message':{'content':json.dumps({'estabelecimento':'Mercado', 'itens':[{'descricao':'LEITE'}]})}})
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    data = asyncio.run(reader.analisar_comprovante(imagem))
    assert data['valor_total'] is data['data_despesa'] is data['itens'][0]['quantidade'] is None
    assert data['cadastro_cnpj']['status'] == 'nao_identificado'


@pytest.mark.parametrize('campos_lidos,endereco_cadastral', [
    ({}, 'Rua do Cadastro, 10'),
    ({'estabelecimento': 'Nome lido', 'endereco': 'Endereço lido'}, 'Rua do Cadastro, 10'),
    ({'estabelecimento': 'Nome lido', 'endereco': 'Endereço lido'}, None),
])
def test_scan_preenche_estabelecimento_pelo_cnpj(setup, imagem, monkeypatch, campos_lidos, endereco_cadastral):
    client, sessions = setup
    original = httpx.AsyncClient
    lido = {'cnpj': '11.222.333/0001-81', **campos_lidos}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'message': {'content': json.dumps(lido)}}))
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    cadastro = {
        'status': 'sucesso', 'validado': True, 'cnpj': '11222333000181',
        'razao_social': 'Mercado Cadastrado LTDA', 'nome_fantasia': 'Mercado Cadastrado',
        'endereco': endereco_cadastral, 'situacao_cadastral': 'ATIVA',
    }
    def consultar(cnpj):
        assert cnpj == lido['cnpj']
        return cadastro
    monkeypatch.setattr(reader, 'consultar_cnpj', consultar)

    response = client.post('/api/scan', files={'imagem': ('a.png', imagem, 'image/png')})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['estabelecimento'] == cadastro['razao_social']
    assert data['cnpj'] == cadastro['cnpj']
    assert data['endereco'] == (endereco_cadastral or campos_lidos.get('endereco'))
    assert data['fonte_estabelecimento'] == 'cadastro_cnpj'
    assert data['cadastro_cnpj'] == cadastro
    if campos_lidos:
        assert data['estabelecimento_lido_imagem'] == campos_lidos['estabelecimento']
        if endereco_cadastral:
            assert data['endereco_lido_imagem'] == campos_lidos['endereco']
    for campo in ('data_despesa', 'hora_despesa', 'valor_total', 'valor_pago', 'desconto_total'):
        assert data[campo] is None
    assert data['itens'] == []
    assert contagem(sessions, Estabelecimento) == contagem(sessions, Despesa) == 0


@pytest.mark.parametrize('status', ['indisponivel', 'nao_encontrado', 'desativada', 'cnpj_invalido'])
def test_leitura_preserva_imagem_sem_cadastro_validado(imagem, monkeypatch, status):
    original = httpx.AsyncClient
    lido = {'cnpj': '11.222.333/0001-81', 'estabelecimento': 'Nome lido', 'endereco': 'Endereço lido', 'valor_total': 10}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'message': {'content': json.dumps(lido)}}))
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    monkeypatch.setattr(reader, 'consultar_cnpj', lambda _: {'status': status, 'validado': False})
    data = asyncio.run(reader.analisar_comprovante(imagem))
    assert all(data[campo] == valor for campo, valor in lido.items())
    assert 'fonte_estabelecimento' not in data


def test_preparar_imagem_nao_decodifica_qrcode(monkeypatch):
    import cv2
    chave = '32200861585865036776650080001128861599661707'
    qr = cv2.QRCodeEncoder_create().encode(f'https://documento.exemplo/qrcode?p={chave}|2|1')
    qr = cv2.copyMakeBorder(qr, 6, 6, 6, 6, cv2.BORDER_CONSTANT, value=255)
    qr = cv2.resize(qr, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
    _, png = cv2.imencode('.png', qr)
    monkeypatch.setattr(cv2, 'QRCodeDetector', lambda: pytest.fail('Não deve detectar QR Code'))
    assert isinstance(reader.preparar_imagem(png.tobytes()), bytes)


def test_timeout_ollama(imagem, monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        raise httpx.ReadTimeout('Timeout simulado', request=request)
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(HTTPException) as error:
        asyncio.run(reader.analisar_comprovante(imagem))
    assert error.value.status_code == 504


def test_qrcode_generico_nao_inventa_tipo_ou_chave(imagem, monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(reader, 'preparar_imagem', lambda _: imagem)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'message': {'content': '{"estabelecimento":"Loja"}'}}))
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    data = asyncio.run(reader.analisar_comprovante(imagem))
    assert not data.get('qrcode_identificado')
    assert data['documento_tipo'] is data['documento_chave'] is None


def test_copia_para_ia_reduz_resolucao_sem_alterar_original(monkeypatch):
    monkeypatch.setattr(reader.settings, 'ollama_image_max_side', 1600)
    buffer = BytesIO()
    Image.new('RGB', (2400, 3200), 'white').save(buffer, 'PNG')
    original = buffer.getvalue()
    processada = reader.preparar_imagem(original)
    with Image.open(BytesIO(processada)) as imagem:
        assert imagem.size == (1200, 1600)
    with Image.open(BytesIO(original)) as imagem:
        assert imagem.size == (2400, 3200)


def test_consulta_cnpj_retorna_endereco_separado_sem_gravar(setup):
    client, sessions = setup
    response = client.get('/api/estabelecimentos/cnpj/11222333000181')
    assert response.status_code == 200
    assert response.json()['endereco_campos'] == {'logradouro': 'Rua A', 'numero': '1'}
    assert contagem(sessions, Estabelecimento) == 0


@pytest.mark.parametrize('estabelecimento', [
    {'cnpj': '11.222.333/0001-81'},
    {'cnpj': '11222333000181', 'nome': 'Nome adulterado', 'endereco': 'Endereço adulterado'},
])
def test_salvamento_usa_apenas_nome_e_endereco_do_cnpj(setup, imagem, dados, estabelecimento):
    client, _ = setup
    dados['estabelecimento'] = estabelecimento
    response = salvar(client, dados, imagem)
    assert response.status_code == 201, response.text
    salvo = client.get(f"/api/despesas/{response.json()['id']}").json()['estabelecimento']
    assert salvo == {'cnpj': '11222333000181', 'nome': 'Mercado Teste', 'endereco': 'Rua A, 1'}


@pytest.mark.parametrize('cnpj', [None, '', '123', '11.222.333/0001-80', 'aaaaaaaaaaaaaa'])
def test_exige_cnpj_valido_antes_de_consultar(setup, imagem, dados, monkeypatch, cnpj):
    client, sessions = setup
    monkeypatch.setattr(despesas, 'consultar_cnpj', lambda _: pytest.fail('Não deve consultar CNPJ inválido'))
    dados['estabelecimento']['cnpj'] = cnpj
    assert salvar(client, dados, imagem).status_code == 422
    assert contagem(sessions, Estabelecimento) == contagem(sessions, Despesa) == 0


@pytest.mark.parametrize('cadastro,status', [
    ({'status': 'indisponivel', 'validado': False}, 503),
    ({'status': 'desativada', 'validado': False}, 503),
    ({'status': 'nao_encontrado', 'validado': False}, 422),
    ({'status': 'sucesso', 'validado': True, 'cnpj': '93209765067025', 'razao_social': 'Outra empresa'}, 422),
])
def test_nao_salva_cadastro_nao_confirmado(setup, imagem, dados, monkeypatch, cadastro, status):
    client, sessions = setup
    monkeypatch.setattr(despesas, 'consultar_cnpj', lambda _: cadastro)
    response = salvar(client, dados, imagem)
    assert response.status_code == status
    assert response.json()['detail']['campos'][0]['campo'] == 'estabelecimento.cnpj'
    assert contagem(sessions, Estabelecimento) == contagem(sessions, Despesa) == 0


def test_cadastro_sem_endereco_nao_reutiliza_endereco_enviado_ou_anterior(setup, imagem, dados, monkeypatch):
    client, _ = setup
    dados.pop('documento_chave')
    assert salvar(client, dados, imagem).status_code == 201
    monkeypatch.setattr(despesas, 'consultar_cnpj', lambda cnpj: {
        'status': 'sucesso', 'validado': True, 'cnpj': cnpj, 'razao_social': 'Mercado Teste', 'endereco': None,
    })
    response = salvar(client, dados, imagem)
    assert response.status_code == 201
    assert client.get(f"/api/despesas/{response.json()['id']}").json()['estabelecimento']['endereco'] is None


def test_itens_sem_gtin_preservam_apresentacao_e_desconto(setup, imagem, dados):
    client, _ = setup
    dados['itens'][0].update(apresentacao='1X2L', unidade='UND', desconto='0.83', preco_total='9.17')
    response = salvar(client, dados, imagem)
    assert response.status_code == 201
    item = client.get(f"/api/despesas/{response.json()['id']}").json()['itens'][0]
    assert 'gtin' not in item
    assert item['apresentacao'] == '1X2L'
    assert item['unidade'] == 'UND'
    assert item['desconto'] == 0.83


def test_salva_descontos_sem_descontar_duas_vezes(setup, imagem, dados):
    client, _ = setup
    dados['itens'][0].update(desconto='2.00', preco_total='8.00')
    dados.update(desconto_total='3.00', valor_pago='7.00')
    response = salvar(client, dados, imagem)
    assert response.status_code == 201, response.text
    detail = client.get(f"/api/despesas/{response.json()['id']}").json()
    assert detail['valor_total'] == 10
    assert detail['desconto_total'] == 3
    assert detail['valor_pago'] == 7
    assert detail['itens'][0]['preco_total'] == 8


@pytest.mark.parametrize('alteracao', [
    {'itens': [{'descricao': 'Leitura inconsistente', 'quantidade': 1, 'preco_unitario': 9.99, 'preco_total': 19.99}]},
    {'itens': [{'descricao': 'Desconto inconsistente', 'quantidade': 2, 'preco_unitario': 5, 'desconto': 2, 'preco_total': 10}]},
    {'itens': [{'descricao': 'Desconto excessivo', 'quantidade': 2, 'preco_unitario': 5, 'desconto': 11}]},
    {'desconto_total': '11.00'},
    {'desconto_total': '2.00', 'valor_pago': '10.00'},
    {'desconto_total': '0.00', 'itens': [{'descricao': 'Item com desconto', 'quantidade': 2, 'preco_unitario': 5, 'preco_total': 8}]},
])
def test_rejeita_valores_incoerentes_dos_itens_e_pagamento(setup, imagem, dados, alteracao):
    client, sessions = setup
    dados.update(alteracao)
    assert salvar(client, dados, imagem).status_code == 422
    assert contagem(sessions, Despesa) == contagem(sessions, ItemDespesa) == 0


def test_scan_calcula_descontos_e_totais_com_origem(imagem, monkeypatch):
    original = httpx.AsyncClient
    lido = {'itens': [{'descricao': 'Leite', 'quantidade': 2, 'preco_unitario': 5, 'preco_total': 8}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'message': {'content': json.dumps(lido)}}))
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    data = asyncio.run(reader.analisar_comprovante(imagem))
    assert data['itens'][0]['desconto'] == 2
    assert data['valor_total'] == 10
    assert data['desconto_total'] == 2
    assert data['valor_pago'] == 8
    assert set(data['campos_calculados']) == {'itens.0.desconto', 'valor_total', 'desconto_total', 'valor_pago'}


def test_salvar_chave_sem_validar_formato(setup, imagem, dados):
    client, _ = setup
    dados["documento_chave"] = "123"
    assert salvar(client, dados, imagem).status_code == 201


def corrigir(client, id, dados):
    return client.put(f'/api/despesas/{id}', json=dados)


@pytest.fixture
def salva(setup, imagem, dados):
    client, _ = setup
    dados['qrcode_identificado'] = True
    dados['valor_total'] = '13.00'
    dados['itens'].append({'codigo': '002', 'descricao': 'Pão', 'quantidade': '1', 'preco_unitario': '3.00'})
    response = salvar(client, dados, imagem)
    assert response.status_code == 201, response.text
    return client.get(f"/api/despesas/{response.json()['id']}").json()


def correcao(detail, **alteracoes):
    campos = ('data_despesa', 'hora_despesa', 'valor_total', 'desconto_total', 'valor_pago', 'forma_pagamento', 'documento_tipo', 'documento_chave')
    return {'estabelecimento': {'cnpj': detail['estabelecimento']['cnpj']}, **{c: detail[c] for c in campos}, 'itens': [
        {k: item[k] for k in ('id', 'codigo', 'descricao', 'quantidade', 'unidade', 'preco_unitario', 'desconto', 'preco_total')}
        for item in detail['itens']
    ], **alteracoes}


def test_correcao_edita_inclui_e_remove_itens_preservando_envio_original(setup, imagem, salva):
    client, sessions = setup
    leite = {**correcao(salva)['itens'][0], 'descricao': 'Leite desnatado', 'quantidade': '3', 'preco_total': '15.00'}
    cafe = {'descricao': 'Café', 'quantidade': '1', 'preco_unitario': '4.00'}
    response = corrigir(client, salva['id'], correcao(salva, data_despesa='2026-10-05', forma_pagamento='Pix', valor_total='19.00', itens=[leite, cafe]))
    assert response.status_code == 200, response.text
    assert response.json() == {'id': salva['id'], 'mensagem': 'Despesa atualizada com sucesso!', 'quantidade_itens': 2}
    detail = client.get(f"/api/despesas/{salva['id']}").json()
    assert (detail['data_despesa'], detail['forma_pagamento'], detail['valor_total'], detail['quantidade_itens']) == ('2026-10-05', 'Pix', 19, 2)
    assert [(i['id'], i['descricao'], i['descricao_original']) for i in detail['itens']] == [
        (leite['id'], 'Leite desnatado', 'LEITE INT'), (detail['itens'][1]['id'], 'Café', 'Café'),
    ]
    assert detail['itens'][1]['id'] not in {i['id'] for i in salva['itens']}
    assert detail['criado_em'] == salva['criado_em'] and detail['atualizado_em']
    assert detail['qrcode_identificado'] is True
    assert client.get(f"/api/despesas/{salva['id']}/imagem").content == imagem
    assert contagem(sessions, ItemDespesa) == 2


def test_correcao_exige_proprietario_e_itens_da_propria_despesa(setup, imagem, dados, salva):
    client, _ = setup
    assert corrigir(client, salva['id'], correcao(salva, usuario_id=2)).status_code == 422
    dados.pop('documento_chave')
    outra = client.get(f"/api/despesas/{salvar(client, dados, imagem).json()['id']}").json()
    alheio = correcao(salva)
    alheio['itens'][0]['id'] = outra['itens'][0]['id']
    response = corrigir(client, salva['id'], alheio)
    assert response.status_code == 422
    assert response.json()['detail']['campos'][0]['campo'] == 'itens.0.id'
    repetido = correcao(salva)
    repetido['itens'][1]['id'] = repetido['itens'][0]['id']
    assert corrigir(client, salva['id'], repetido).status_code == 422
    client.cookies.set('poupescan_session', criar_token_acesso(2))
    assert corrigir(client, salva['id'], correcao(salva, forma_pagamento='Invasão')).status_code == 404
    assert corrigir(client, 999999, correcao(salva)).status_code == 404
    client.cookies.set('poupescan_session', criar_token_acesso(1))
    assert client.get(f"/api/despesas/{salva['id']}").json() == salva
    assert client.get(f"/api/despesas/{outra['id']}").json() == outra


@pytest.mark.parametrize('alteracao', [
    {'itens': []}, {'valor_total': '99.00'}, {'data_despesa': ''}, {'qrcode_identificado': False},
    {'desconto_total': '1.00', 'valor_pago': '13.00'},
])
def test_correcao_invalida_nao_altera_nada(setup, salva, alteracao):
    client, _ = setup
    assert corrigir(client, salva['id'], correcao(salva, forma_pagamento='Pix', **alteracao)).status_code == 422
    assert client.get(f"/api/despesas/{salva['id']}").json() == salva


def test_correcao_desfaz_tudo_se_um_item_falhar(setup, salva, monkeypatch):
    client, sessions = setup
    original = despesas.resolver_produto
    def falhar_no_novo(db, estabelecimento_id, item):
        if item.codigo == '003':
            raise SQLAlchemyError('Falha simulada no item novo')
        return original(db, estabelecimento_id, item)
    monkeypatch.setattr(despesas, 'resolver_produto', falhar_no_novo)
    payload = correcao(salva, forma_pagamento='Pix', valor_total='9.00')
    payload['itens'] = [payload['itens'][1], {'codigo': '003', 'descricao': 'Café', 'quantidade': '2', 'preco_unitario': '3.00'}]
    assert corrigir(client, salva['id'], payload).status_code == 503
    assert client.get(f"/api/despesas/{salva['id']}").json() == salva
    assert contagem(sessions, ItemDespesa) == 2


def test_correcao_limita_tamanho_e_rejeita_json_invalido(setup, salva):
    client, _ = setup
    assert client.put(f"/api/despesas/{salva['id']}", content=b'x' * (1024 * 1024 + 1)).status_code == 413
    assert client.put(f"/api/despesas/{salva['id']}", content=b'not json').status_code == 422


def test_correcao_sem_troca_de_cnpj_nao_consulta_cadastro(setup, salva, monkeypatch):
    client, _ = setup
    monkeypatch.setattr(despesas, 'consultar_cnpj', lambda _: pytest.fail('Não deve consultar o CNPJ já salvo'))
    payload = correcao(salva, forma_pagamento='Dinheiro')
    payload['estabelecimento']['cnpj'] = '11.222.333/0001-81'
    assert corrigir(client, salva['id'], payload).status_code == 200
    assert client.get(f"/api/despesas/{salva['id']}").json()['estabelecimento'] == salva['estabelecimento']


def test_correcao_com_novo_cnpj_confirma_cadastro_e_troca_estabelecimento(setup, salva, monkeypatch):
    client, sessions = setup
    payload = correcao(salva)
    payload['estabelecimento'] = {'cnpj': '93209765067025', 'nome': 'Nome adulterado'}
    monkeypatch.setattr(despesas, 'consultar_cnpj', lambda _: {'status': 'indisponivel', 'validado': False})
    response = corrigir(client, salva['id'], payload)
    assert response.status_code == 503
    assert response.json()['detail']['campos'][0]['campo'] == 'estabelecimento.cnpj'
    assert client.get(f"/api/despesas/{salva['id']}").json() == salva
    monkeypatch.setattr(despesas, 'consultar_cnpj', lambda cnpj: {
        'status': 'sucesso', 'validado': True, 'cnpj': cnpj, 'razao_social': 'Outro Mercado', 'endereco': 'Rua B, 2',
    })
    assert corrigir(client, salva['id'], payload).status_code == 200
    detail = client.get(f"/api/despesas/{salva['id']}").json()
    assert detail['estabelecimento'] == {'cnpj': '93209765067025', 'nome': 'Outro Mercado', 'endereco': 'Rua B, 2'}
    with sessions() as db:
        locais = db.scalars(select(ProdutoEstabelecimento.codigo).join(Estabelecimento).where(Estabelecimento.cnpj == '93209765067025')).all()
    assert sorted(locais) == ['001', '002']
    assert contagem(sessions, Estabelecimento) == 2


def test_correcao_rejeita_chave_de_outra_despesa_do_usuario(setup, imagem, dados, salva):
    client, _ = setup
    dados['documento_chave'] = '2' * 44
    segunda = client.get(f"/api/despesas/{salvar(client, dados, imagem).json()['id']}").json()
    response = corrigir(client, segunda['id'], correcao(segunda, documento_chave=salva['documento_chave']))
    assert response.status_code == 409
    assert response.json()['detail'] == 'Este comprovante já está cadastrado na sua conta.'
    assert client.get(f"/api/despesas/{segunda['id']}").json() == segunda
    assert corrigir(client, segunda['id'], correcao(segunda, forma_pagamento='Pix')).status_code == 200


def test_cors_permite_correcao_pelo_live_server(setup):
    client, _ = setup
    response = client.options('/api/despesas/1', headers={
        'Origin': 'http://127.0.0.1:5500', 'Access-Control-Request-Method': 'PUT', 'Access-Control-Request-Headers': 'content-type',
    })
    assert response.status_code == 200
    assert 'PUT' in response.headers['access-control-allow-methods']
