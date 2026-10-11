import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite://')

import pytest
from backend.app.services import cadastro_cnpj as cadastro


@pytest.fixture(autouse=True)
def cache_limpo():
    cadastro._CACHE.clear()
    yield
    cadastro._CACHE.clear()


def test_endereco_separado_preserva_componentes_da_fonte():
    dados = {
        'cnpj': '11.222.333/0001-81', 'razao_social': 'Mercado Teste',
        'descricao_tipo_de_logradouro': ' RUA ', 'logradouro': 'DOS TESTES', 'numero': '10',
        'complemento': 'LOJA 2, FUNDOS', 'bairro': 'CENTRO', 'municipio': 'SERRA', 'uf': 'ES', 'cep': '29160000',
    }
    resultado = cadastro._normalizar_resposta(dados, '11222333000181')
    assert resultado['endereco_campos'] == {
        'logradouro': 'RUA DOS TESTES', 'numero': '10', 'complemento': 'LOJA 2, FUNDOS',
        'bairro': 'CENTRO', 'municipio': 'SERRA', 'uf': 'ES', 'cep': '29160-000',
    }
    assert resultado['endereco'] == 'RUA DOS TESTES, 10, LOJA 2, FUNDOS, CENTRO, SERRA, ES, CEP 29160-000'


def test_endereco_ausente_nao_e_inventado():
    resultado = cadastro._normalizar_resposta({'cnpj': '11222333000181', 'razao_social': 'Loja'}, '11222333000181')
    assert resultado['endereco'] is None
    assert all(value is None for value in resultado['endereco_campos'].values())


def test_rejeita_resposta_de_outro_cnpj():
    with pytest.raises(ValueError, match='diferente'):
        cadastro._normalizar_resposta({'cnpj': '93209765067025', 'razao_social': 'Outra loja'}, '11222333000181')


@pytest.mark.parametrize('valor', ['', '123', '11.222.333/0001-80'])
def test_invalido_nao_consulta_servico(monkeypatch, valor):
    monkeypatch.setattr(cadastro, '_consultar_sem_cache', lambda _: pytest.fail('CNPJ inválido não deve ser enviado'))
    assert cadastro.consultar_cnpj(valor)['validado'] is False


def test_falha_permite_retentativa_e_cache_protege_endereco(monkeypatch):
    sucesso = cadastro._normalizar_resposta({'cnpj': '11222333000181', 'razao_social': 'Loja', 'logradouro': 'Rua A'}, '11222333000181')
    respostas = iter([{'status': 'indisponivel', 'validado': False}, sucesso])
    monkeypatch.setattr(cadastro, '_consultar_sem_cache', lambda _: next(respostas))
    assert cadastro.consultar_cnpj('11222333000181')['status'] == 'indisponivel'
    resultado = cadastro.consultar_cnpj('11.222.333/0001-81')
    assert resultado['status'] == 'sucesso'
    resultado['endereco_campos']['logradouro'] = 'Alterado'
    assert cadastro.consultar_cnpj('11222333000181')['endereco_campos']['logradouro'] == 'Rua A'
