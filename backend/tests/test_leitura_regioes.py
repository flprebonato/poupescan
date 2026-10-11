import asyncio
import base64
from io import BytesIO
import json

import httpx
from PIL import Image, ImageDraw
import pytest
from fastapi import HTTPException

from backend.app.services import reader


@pytest.fixture
def foto():
    imagem = Image.new('RGB', (600, 1600), '#151515')
    ImageDraw.Draw(imagem).rectangle((100, 0, 500, 1599), fill='#dddddd')
    buffer = BytesIO()
    imagem.save(buffer, 'PNG')
    return buffer.getvalue()


def chave_teste():
    base = '32' + '2604' + '11222333000181' + '65' + '001' + '000000001' + '1' + '00000001'
    soma = sum(int(d) * (2 + i % 8) for i, d in enumerate(reversed(base)))
    digito = 11 - soma % 11
    return base + str(0 if digito >= 10 else digito)


def simular(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(reader, 'consultar_cnpj', lambda cnpj: {'status': 'desativada', 'validado': False})


def resposta(data):
    return httpx.Response(200, json={'message': {'content': json.dumps(data)}})


def test_recortes_preservam_resolucao_e_removem_margens(foto):
    with Image.open(BytesIO(foto)) as original:
        papel = reader.recortar_papel(original)
        assert 400 <= papel.width <= 450
        assert papel.height == 1600
    recortes = reader.preparar_recortes(foto)
    with Image.open(BytesIO(recortes['cabecalho'])) as cabecalho:
        assert cabecalho.height == 448
        assert cabecalho.width == papel.width
    with Image.open(BytesIO(recortes['resumo'])) as resumo:
        assert resumo.height == 1040
    with Image.open(BytesIO(foto)) as original:
        assert original.size == (600, 1600)


def test_releitura_recupera_cnpj_e_resumo_sem_duplicar_itens(foto, monkeypatch):
    chamadas = []
    itens = [{'descricao': 'Item', 'quantidade': 1, 'preco_unitario': 250.44, 'preco_total': 243.90}]
    def handler(request):
        body = json.loads(request.content)
        schema = body['format']
        etapa = schema['title']
        chamadas.append(etapa)
        assert set(schema['required']) == set(schema['properties'])
        with Image.open(BytesIO(base64.b64decode(body['messages'][0]['images'][0]))) as recorte:
            if etapa == 'CabecalhoLido':
                assert recorte.height < 500
        if etapa == 'ComprovanteLido':
            return resposta({'itens': itens, 'documento_tipo': 'NÃO É DOCUMENTO FISCAL', 'documento_chave': '123456789012345'})
        if etapa == 'CabecalhoLido':
            return resposta({'cnpj': '11.222.333/0001-81', 'estabelecimento': 'Nome lido'})
        return resposta({'valor_total': 250.44, 'desconto_total': 6.54, 'valor_pago': 243.9,
                         'data_despesa': '2026-04-23', 'hora_despesa': '18:57:18',
                         'documento_chave': chave_teste(), 'documento_tipo': 'NFC-e', 'forma_pagamento': 'Cartão de crédito'})
    simular(monkeypatch, handler)
    consultas = []
    def cadastro(cnpj):
        consultas.append(cnpj)
        return {'status': 'sucesso', 'validado': True, 'cnpj': '11222333000181',
                'razao_social': 'Estabelecimento cadastrado', 'endereco': 'Rua do cadastro, 1'}
    monkeypatch.setattr(reader, 'consultar_cnpj', cadastro)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'CabecalhoLido', 'ResumoLido']
    assert consultas == ['11.222.333/0001-81']
    assert data['estabelecimento'] == 'Estabelecimento cadastrado'
    assert data['cnpj'] == '11222333000181'
    assert (data['valor_total'], data['desconto_total'], data['valor_pago']) == (250.44, 6.54, 243.9)
    assert data['documento_chave'] == chave_teste()
    assert data['documento_tipo'] == 'NFC-e'
    assert len(data['itens']) == 1
    assert all(data['itens'][0][k] == v for k, v in itens[0].items())
    assert 'valor_total' not in data['campos_calculados']


def test_chave_nao_e_usada_para_recuperar_cnpj(foto, monkeypatch):
    chamadas = []
    def handler(request):
        chamadas.append(json.loads(request.content)['format']['title'])
        return resposta({'documento_chave': chave_teste(), 'valor_total': 10, 'desconto_total': 0,
                         'valor_pago': 10, 'forma_pagamento': 'Dinheiro', 'data_despesa': '2026-04-23', 'hora_despesa': '12:00:00',
                         'itens': [{'descricao': 'Item', 'quantidade': 1, 'preco_unitario': 10, 'preco_total': 10}]})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert data['cnpj'] is None
    assert chamadas == ['ComprovanteLido', 'CabecalhoLido']


@pytest.mark.parametrize('falha', ['timeout', 'json', 'http', 'truncado'])
def test_falha_na_releitura_preserva_dados_e_informa_revisao(foto, monkeypatch, falha):
    def handler(request):
        if json.loads(request.content)['format']['title'] == 'ComprovanteLido':
            return resposta({'estabelecimento': 'Loja lida', 'valor_total': 10})
        if falha == 'timeout':
            raise httpx.ReadTimeout('simulado', request=request)
        if falha == 'json':
            return httpx.Response(200, json={'message': {'content': 'inválido'}})
        if falha == 'truncado':
            return httpx.Response(200, json={'done_reason': 'length', 'message': {'content': '{}'}})
        return httpx.Response(503)
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert data['estabelecimento'] == 'Loja lida'
    assert data['valor_total'] == 10
    assert data['cnpj'] is data['data_despesa'] is None
    assert len(data['avisos_leitura']) == 4


def test_releitura_itens_substitui_somente_quando_confere(foto, monkeypatch):
    itens = [{'descricao': 'Item', 'quantidade': 2, 'preco_unitario': 5, 'preco_total': 10}]
    chamadas = []
    def handler(request):
        etapa = json.loads(request.content)['format']['title']
        chamadas.append(etapa)
        if etapa == 'ItensLidos':
            return resposta({'itens': itens})
        return resposta({'documento_chave': chave_teste(), 'valor_total': 10, 'desconto_total': 0,
                         'valor_pago': 10, 'forma_pagamento': 'Dinheiro', 'data_despesa': '2026-04-23', 'hora_despesa': '12:00:00',
                         'itens': [{**itens[0], 'quantidade': 1}]})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'CabecalhoLido', 'ItensLidos', 'TotaisImpressos']
    assert data['itens'][0]['quantidade'] == 2


def test_releitura_itens_divergente_nao_substitui_original(foto, monkeypatch):
    original = [{'descricao': 'Item original', 'quantidade': 1, 'preco_unitario': 5, 'preco_total': 5}]
    def handler(request):
        if json.loads(request.content)['format']['title'] == 'ItensLidos':
            return resposta({'itens': [{'descricao': 'Outro item', 'quantidade': 1, 'preco_unitario': 20}]})
        return resposta({'documento_chave': chave_teste(), 'valor_total': 10, 'desconto_total': 0,
                         'valor_pago': 10, 'forma_pagamento': 'Dinheiro', 'data_despesa': '2026-04-23', 'hora_despesa': '12:00:00',
                         'itens': original})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert data['itens'][0]['descricao'] == 'Item original'
    assert any('produtos não fechou' in aviso for aviso in data['avisos_leitura'])


def test_protocolo_nao_vira_chave_nem_cnpj(foto, monkeypatch):
    simular(monkeypatch, lambda _: resposta({'estabelecimento': 'Loja', 'documento_chave': '123456789012345'}))
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert data['cnpj'] is None


def test_resposta_principal_truncada_nao_passa_como_leitura_completa(foto, monkeypatch):
    simular(monkeypatch, lambda _: httpx.Response(200, json={'done_reason': 'length', 'message': {'content': '{"valor_total":10}'}}))
    with pytest.raises(HTTPException) as error:
        asyncio.run(reader.analisar_comprovante(foto))
    assert error.value.status_code == 502


def test_chave_incompleta_rele_somente_chave_sem_aviso_fiscal(foto, monkeypatch):
    chamadas = []
    def handler(request):
        chamadas.append(json.loads(request.content)['format']['title'])
        return resposta({'cnpj': '11222333000181', 'documento_chave': '123',
                         'valor_total': 10, 'desconto_total': 0, 'valor_pago': 10,
                         'forma_pagamento': 'Dinheiro', 'data_despesa': '2026-04-23',
                         'hora_despesa': '12:00:00',
                         'itens': [{'descricao': 'Item', 'quantidade': 1, 'preco_unitario': 10, 'preco_total': 10}]})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'ChaveLida']
    assert data['documento_chave'] == '123'
    assert not data.get('avisos_leitura')


@pytest.mark.parametrize('modo', ['recuperados', 'ausentes', 'falha', 'excessivos'])
def test_confere_descontos_mesmo_com_total_bruto_correto(foto, monkeypatch, modo):
    valores = [15.99,9.79,7.99,27.93,19.98,48.90,13.99,30,4.76,1.99,9.29,13.98,27.96,2.99,14.90]
    descontos = {1:0.83,3:1.40,4:1,5:2.94,8:0.37}
    itens = [{'codigo': str(i), 'descricao': f'Produto {i}', 'quantidade': 1,
              'preco_unitario': valor, 'preco_total': valor} for i, valor in enumerate(valores)]
    chamadas = []
    def handler(request):
        etapa = json.loads(request.content)['format']['title']
        chamadas.append(etapa)
        if etapa == 'ItensLidos':
            if modo == 'falha':
                return httpx.Response(503)
            if modo == 'ausentes':
                return resposta({'itens': itens})
            candidatos = [{**item, 'desconto': descontos.get(i),
                           'preco_total': None if i in descontos else item['preco_total']}
                          for i, item in enumerate(itens)]
            if modo == 'excessivos':
                candidatos[0]['desconto'] = 1
                candidatos[0]['preco_total'] = None
            return resposta({'itens': candidatos})
        return resposta({'cnpj': '11222333000181', 'data_despesa': '2026-04-23',
                         'hora_despesa': '18:57:18', 'forma_pagamento': 'Cartão',
                         'valor_total': 250.44, 'valor_pago': 243.90, 'desconto_total': 6.54,
                         'itens': itens})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'DescontosLidos', 'DescontosLidos', 'ItensLidos']
    if modo == 'recuperados':
        assert not data.get('avisos_leitura')
        assert sum(item['preco_total'] for item in data['itens']) == pytest.approx(243.90)
        for i, item in enumerate(data['itens']):
            assert item['desconto'] == descontos.get(i, 0)
    else:
        assert any('descontos dos itens não conferem' in aviso for aviso in data['avisos_leitura'])
        assert all(item['desconto'] is None for item in data['itens'])
        assert sum(item['preco_total'] for item in data['itens']) == pytest.approx(250.44)


def test_descontos_por_codigo_sem_substituir_tabela(foto, monkeypatch):
    chamadas = []
    itens = [
        {'codigo': 'AR014246', 'descricao': 'REF.COCA-COLA ZERO', 'quantidade': 1, 'preco_unitario': 9.79, 'preco_total': 9.79},
        {'codigo': 'AR037578', 'descricao': 'CONTRA F.FRIBOI PORC', 'quantidade': 0.98, 'preco_unitario': 49.9, 'preco_total': 48.90},
        {'codigo': 'AR036879', 'descricao': 'HF.UVA ITALIA', 'quantidade': 1, 'preco_unitario': 13.99, 'preco_total': 13.99},
    ]
    def handler(request):
        body = json.loads(request.content)
        etapa = body['format']['title']
        chamadas.append(etapa)
        if etapa == 'DescontosLidos':
            with Image.open(BytesIO(base64.b64decode(body['messages'][0]['images'][0]))) as recorte:
                assert recorte.height < 800
            # Mesmo desconto aparece em ambos os recortes; não pode duplicar.
            return resposta({'descontos': [
                {'codigo': 'AR037578', 'descricao': 'Contra filé', 'desconto': 2.94},
                {'codigo': 'AR014246', 'descricao': 'Coca Cola', 'desconto': 0.83},
            ]})
        assert etapa == 'ComprovanteLido'
        return resposta({'cnpj': '11222333000181', 'data_despesa': '2026-04-23',
                         'hora_despesa': '18:57:18', 'forma_pagamento': 'Cartão',
                         'valor_total': 72.68, 'valor_pago': 68.91, 'desconto_total': 3.77,
                         'itens': itens})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'DescontosLidos', 'DescontosLidos']
    assert [item['desconto'] for item in data['itens']] == [0.83, 2.94, 0]
    assert [item['preco_total'] for item in data['itens']] == [8.96, 45.96, 13.99]
    assert [item['descricao'] for item in data['itens']] == [item['descricao'] for item in itens]
    assert not data.get('avisos_leitura')


@pytest.mark.parametrize('descontos', [
    [{'codigo': 'outro', 'desconto': 2}],
    [{'codigo': 'A', 'desconto': 2}, {'codigo': 'A', 'desconto': 3}],
    [{'codigo': 'A', 'desconto': 11}],
    [{'codigo': 'A', 'desconto': 4}],
])
def test_nao_aplica_desconto_sem_vinculo_ou_incoerente(descontos):
    item = {'codigo': 'A', 'descricao': 'Produto', 'quantidade': 1, 'preco_unitario': 10, 'preco_total': 10}
    dados = {'valor_total': 10, 'desconto_total': 3, 'itens': [dict(item)]}
    reader.aplicar_descontos_lidos(dados, descontos)
    assert dados['itens'] == [item]


def test_numero_nfce_substituido_por_chave_impressa(foto, monkeypatch):
    chamadas = []
    chave = '3226' + '0493' + '2097' + '6506' + '7025' + '6552' + '4000' + '1589' + '5410' + '4657' + '9171'
    def handler(request):
        etapa = json.loads(request.content)['format']['title']
        chamadas.append(etapa)
        if etapa == 'ChaveLida':
            return resposta({'documento_chave': ' '.join(chave[i:i+4] for i in range(0,44,4))})
        return resposta({'cnpj': '11222333000181', 'data_despesa': '2026-04-23',
                         'hora_despesa': '18:57:18', 'forma_pagamento': 'Cartão',
                         'valor_total': 10, 'valor_pago': 10, 'desconto_total': 0,
                         'documento_chave': '000158954', 'documento_tipo': 'NFC-e',
                         'itens': [{'descricao': 'Produto', 'quantidade': 1, 'preco_unitario': 10, 'preco_total': 10}]})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'ChaveLida']
    assert data['documento_chave'] == chave
    assert not data.get('avisos_leitura')


@pytest.mark.parametrize('recupera_produtos', [False, True])
def test_le_descontos_quando_primeira_tabela_esta_incompleta(foto, monkeypatch, recupera_produtos):
    produto = {'codigo': 'A', 'descricao': 'Produto A', 'quantidade': 1, 'preco_unitario': 10, 'preco_total': 10}
    faltante = {'codigo': 'B', 'descricao': 'Produto B', 'quantidade': 1, 'preco_unitario': 5, 'preco_total': 5}
    chamadas = []
    def handler(request):
        etapa = json.loads(request.content)['format']['title']
        chamadas.append(etapa)
        if etapa == 'ItensLidos':
            return resposta({'itens': [produto, faltante] if recupera_produtos else [produto]})
        if etapa == 'DescontosLidos':
            return resposta({'descontos': [{'codigo': 'A', 'desconto': 2}]})
        return resposta({'cnpj': '11222333000181', 'data_despesa': '2026-04-23',
                         'hora_despesa': '18:57:18', 'forma_pagamento': 'Cartão',
                         'valor_total': 15, 'valor_pago': 13, 'desconto_total': 2,
                         'itens': [produto]})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert chamadas == ['ComprovanteLido', 'ItensLidos', 'TotaisImpressos', 'DescontosLidos', 'DescontosLidos']
    assert data['itens'][0]['desconto'] == 2
    assert data['itens'][0]['preco_total'] == 8
    assert len(data['itens']) == (2 if recupera_produtos else 1)
    if recupera_produtos:
        assert not data.get('avisos_leitura')
    else:
        assert any('produtos não fechou' in aviso for aviso in data['avisos_leitura'])


@pytest.mark.parametrize('entrada,esperada', [('19/09/26', '2026-09-19'), ('19/09/2026', '2026-09-19'),
                                           ('2026-09-19', '2026-09-19'), ('31/02/26', None)])
def test_normaliza_data_de_comprovante(entrada, esperada):
    assert reader.ResumoLido(data_despesa=entrada).data_despesa == esperada


def itens_carone():
    valores = [(1,19.99,19.99,None), (2,29.59,59.18,None), (2,7.99,15.98,2),
               (2,7.99,15.98,2), (0.224,59.9,13.42,None), (0.380,89.9,34.16,None),
               (1,7.98,7.98,1.8), (1,8.99,7.49,1.5), (1,2.89,2.89,None),
               (2,3.89,5.58,2.2), (2,5.39,10.78,None)]
    return [{'codigo':str(i+1), 'descricao':f'Produto {i+1}', 'quantidade':q,
             'preco_unitario':u, 'preco_total':n, 'desconto':d,
             'unidade':'KG' if i in (4,5) else 'UN'} for i,(q,u,n,d) in enumerate(valores)]


def test_normaliza_bruto_da_linha_preservando_desconto_e_peso():
    itens = reader.normalizar_itens_lidos(itens_carone())
    data = reader.completar_valores({'itens':itens})
    assert data['valor_total'] == 197.13
    assert data['desconto_total'] == 9.50
    assert data['valor_pago'] == 187.63
    assert [data['itens'][i]['preco_total'] for i in (2,3,6)] == [13.98,13.98,6.18]
    assert [data['itens'][i]['quantidade'] for i in (4,5)] == [0.224,0.380]
    assert [data['itens'][i]['desconto'] for i in (4,5)] == [0,0]


@pytest.mark.parametrize('bruto', [187.63, None])
def test_recupera_totais_sem_perder_descontos_da_primeira_leitura(foto, monkeypatch, bruto):
    chamadas = []
    def handler(request):
        etapa = json.loads(request.content)['format']['title']
        chamadas.append(etapa)
        if etapa == 'TotaisImpressos':
            return resposta({'rotulo_total_bruto':'Valor a Pagar', 'total_bruto_impresso':187.63,
                             'valor_a_pagar_impresso':187.63, 'desconto_total_impresso':9.50})
        if etapa == 'ItensLidos':
            # Simula a regressão vista no modelo real: a segunda leitura perde descontos.
            return resposta({'itens':[{**item,'desconto':None,'preco_total':float(reader.moeda(reader.Decimal(str(item['quantidade']))*reader.Decimal(str(item['preco_unitario']))))} for item in itens_carone()]})
        return resposta({'cnpj':'11222333000181','data_despesa':'19/09/26','hora_despesa':'16:05:43',
                         'forma_pagamento':'Cartão','valor_total':bruto,'valor_pago':167.63,
                         'desconto_total':20,'itens':itens_carone()})
    simular(monkeypatch, handler)
    data = asyncio.run(reader.analisar_comprovante(foto))
    assert data['data_despesa'] == '2026-09-19'
    assert data['hora_despesa'] == '16:05:43'
    assert data['valor_total'] == 197.13
    assert data['desconto_total'] == 9.50
    assert data['valor_pago'] == 187.63
    assert not data.get('avisos_leitura')
    assert chamadas == (['ComprovanteLido','ResumoLido','ItensLidos','TotaisImpressos'] if bruto is None else ['ComprovanteLido','ItensLidos','TotaisImpressos'])


def test_nao_substitui_total_bruto_explicitamente_impresso():
    itens = reader.normalizar_itens_lidos(itens_carone())
    assert reader.reconciliar_totais_impressos(itens, {
        'rotulo_total_bruto':'Total bruto', 'total_bruto_impresso':200,
        'valor_a_pagar_impresso':187.63,'desconto_total_impresso':9.50,
    }) is None
