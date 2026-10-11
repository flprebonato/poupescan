import pytest

from backend.app.schemas.despesa import ComprovanteLido
from backend.app.services.calculos_comprovante import completar_valores


def calcular(itens, **totais):
    return completar_valores(ComprovanteLido(itens=itens, **totais).model_dump())


@pytest.mark.parametrize('item,desconto,liquido', [
    ({'quantidade': 2, 'preco_unitario': 5, 'preco_total': 8}, 2, 8),
    ({'quantidade': 2, 'preco_unitario': 5, 'desconto': 2}, 2, 8),
    ({'quantidade': 0.98, 'preco_unitario': 49.9, 'preco_total': 48.9}, 0, 48.9),
    ({'quantidade': 1, 'preco_unitario': 0, 'preco_total': 0}, 0, 0),
])
def test_completa_valores_dedutiveis(item, desconto, liquido):
    data = calcular([item])
    assert data['itens'][0]['desconto'] == desconto
    assert data['itens'][0]['preco_total'] == liquido
    assert data['desconto_total'] == desconto
    assert data['valor_pago'] == liquido
    assert data['valor_total'] == pytest.approx(liquido + desconto)


@pytest.mark.parametrize('totais', [{'desconto_total': 3}, {'valor_pago': 7}])
def test_desconto_geral_inclui_itens_sem_duplicar(totais):
    data = calcular([{'quantidade': 2, 'preco_unitario': 5, 'preco_total': 8}], **totais)
    assert data['valor_total'] == 10
    assert data['desconto_total'] == 3
    assert data['valor_pago'] == 7
    assert not set(totais).intersection(data['campos_calculados'])


def test_nao_substitui_total_lido_divergente():
    data = calcular([{'quantidade': 2, 'preco_unitario': 97.49, 'preco_total': 194.98}], valor_total=80, desconto_total=0)
    assert data['valor_total'] == 80
    assert data['valor_pago'] is None
    assert data['campos_calculados'] == ['itens.0.desconto']


@pytest.mark.parametrize('item', [
    {'quantidade': 1, 'preco_unitario': 9.99, 'preco_total': 19.99},
    {'quantidade': 2, 'preco_unitario': 5, 'preco_total': 10, 'desconto': 2},
    {'quantidade': 1, 'preco_unitario': 5, 'desconto': 6},
    {'quantidade': None, 'preco_unitario': 5, 'preco_total': 5},
])
def test_nao_forca_fechamento_de_itens_inconsistentes(item):
    data = calcular([item])
    assert data['valor_total'] is data['desconto_total'] is data['valor_pago'] is None
    assert data['campos_calculados'] == []
    assert all(data['itens'][0][key] == value for key, value in item.items())


def test_nao_presume_desconto_zero_sem_total_da_linha():
    data = calcular([{'quantidade': 2, 'preco_unitario': 5}])
    assert data['valor_total'] == 10
    assert data['itens'][0]['preco_total'] is data['itens'][0]['desconto'] is None
    assert data['desconto_total'] is data['valor_pago'] is None


def test_nao_presume_valores_sem_itens():
    data = calcular([])
    assert data['valor_total'] is data['desconto_total'] is data['valor_pago'] is None
    assert data['campos_calculados'] == []


def test_valor_fora_da_faixa_nao_quebra_calculo():
    data = calcular([{'quantidade': 1e300, 'preco_unitario': 5, 'preco_total': 10}])
    assert data['valor_total'] is data['desconto_total'] is data['valor_pago'] is None
    assert data['campos_calculados'] == []


def test_desconto_pendente_nao_pode_ser_exibido_como_zero():
    data = calcular([{'quantidade': 2, 'preco_unitario': 5, 'preco_total': 10}], desconto_total=2)
    assert data['itens'][0]['desconto'] is None
    assert data['valor_total'] == 10
    assert data['valor_pago'] == 8


def test_peso_omitido_nao_vira_desconto_falso():
    data = calcular([{'descricao': 'Quiche', 'quantidade': 1, 'unidade': 'KG',
                     'preco_unitario': 59.90, 'preco_total': 13.42}])
    assert data['itens'][0]['desconto'] is None
    assert data['valor_total'] is None
