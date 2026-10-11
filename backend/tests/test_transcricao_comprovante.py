from decimal import Decimal

import pytest

from backend.app.services.transcricao_comprovante import numero_impresso, valores_desconto, interpretar_itens_transcritos


@pytest.mark.parametrize('texto,esperado', [('0,224', '0.224'), ('0,380', '0.380'),
                                           ('R$ 1.234,56', '1234.56'), ('2', '2')])
def test_numeros_preservam_peso_e_separadores(texto, esperado):
    assert numero_impresso(texto) == Decimal(esperado)


@pytest.mark.parametrize('texto', [None, '', '0.224', '2 UN', '12,3,4', '-2,00', 'NaN'])
def test_coluna_ambigua_exige_revisao(texto):
    with pytest.raises(ValueError):
        numero_impresso(texto)


@pytest.mark.parametrize('linha,desconto,liquido', [
    ('DESCONTO 12,52% R$ -2,00 13,98', '2.00', '13.98'),
    ('DESCONTO 28,28% R$ -2,20 5,58', '2.20', '5.58'),
    ('desconto sobre item 0,83', '0.83', None),
])
def test_separa_percentual_desconto_e_liquido(linha, desconto, liquido):
    assert valores_desconto(linha) == (Decimal(desconto), Decimal(liquido) if liquido else None)


@pytest.mark.parametrize('linha', ['13,42', 'DESCONTO 12,52%', 'DESCONTO 2,00 13,98',
                                  'DESCONTO R$ -2,00 13,98 15,98'])
def test_nao_escolhe_valor_em_linha_ambigua(linha):
    with pytest.raises(ValueError):
        valores_desconto(linha)


def test_desconto_literal_nao_precisa_do_total_liquido_impresso():
    itens = interpretar_itens_transcritos([{
        'descricao': 'Produto', 'quantidade_impressa': '2', 'unidade': 'UN',
        'preco_unitario_impresso': '5,00', 'total_produto_impresso': '10,00',
        'linha_desconto': 'desconto sobre item 2,00',
    }])
    assert itens[0]['desconto'] == 2
    assert itens[0]['preco_total'] is None


@pytest.mark.parametrize('linhas', [
    ['DESCONTO -2,00 8,00'],
    ['002 A Produto 2UN 5,00 10,00'],
    ['001 A Produto 2UN 5,00 10,00', '001 A Produto 2UN 5,00 10,00'],
    ['001 A Produto 2UN 5,00 10,00', 'DESCONTO -2,00 8,00', 'DESCONTO -2,00 8,00'],
    ['001 A Produto ilegível'],
    ['001 A Produto 2UN 5,00 10,00', '002 B Produto ilegível', 'DESCONTO -2,00 8,00'],
])
def test_linhas_ambiguas_ou_fora_de_ordem_nao_sao_omitidas(linhas):
    from backend.app.services.transcricao_comprovante import interpretar_linhas_transcritas
    with pytest.raises(ValueError):
        interpretar_linhas_transcritas(linhas)


def test_produto_em_duas_linhas_preserva_associacao_do_desconto():
    from backend.app.services.transcricao_comprovante import interpretar_linhas_transcritas
    itens = interpretar_linhas_transcritas(['001 A Produto', '2UN 5,00 10,00', 'DESCONTO -2,00 8,00'])
    assert itens[0]['codigo'] == 'A'
    assert itens[0]['desconto'] == 2
    assert itens[0]['preco_total'] == 8
