"""Leitura real do JPEG, habilitada com POUPESCAN_TESTE_REAL=1."""

import asyncio
import json
import os
from pathlib import Path
import re
import unicodedata

from fastapi import HTTPException
import pytest

from backend.app.services import reader


@pytest.mark.skipif(
    os.environ.get('POUPESCAN_TESTE_REAL') != '1',
    reason='Use POUPESCAN_TESTE_REAL=1 para executar a leitura com o Ollama real.',
)
def test_leitura_do_comprovante_jpeg():
    imagem = Path(__file__).parent / 'fixtures' / 'comprovante_teste.jpeg'
    conteudo = imagem.read_bytes()
    reader.validar_imagem(conteudo, 'image/jpeg')
    print(f'\nModelo: {reader.settings.ollama_model}')
    try:
        dados = asyncio.run(reader.analisar_comprovante(conteudo))
    except HTTPException as erro:
        pytest.fail(f'Falha na leitura real ({erro.status_code}): {erro.detail}')
    print(json.dumps(dados, ensure_ascii=False, indent=2))

    # Valores esperados conferidos na imagem; não são enviados à IA.
    assert re.sub(r'\D', '', dados.get('cnpj') or '') == '28129260001233'
    assert dados.get('estabelecimento')
    assert dados.get('endereco')
    assert dados.get('data_despesa') == '2026-09-19'
    assert dados.get('hora_despesa') == '16:07:50'
    assert dados.get('valor_total') == pytest.approx(197.13, abs=0.001)
    assert dados.get('desconto_total') == pytest.approx(9.50, abs=0.001)
    assert dados.get('valor_pago') == pytest.approx(187.63, abs=0.001)
    assert dados.get('documento_chave') == '32260928129260001233652010001446229003709184'
    assert not dados.get('qrcode_identificado')
    assert re.sub(r'[^a-z]', '', (dados.get('documento_tipo') or '').lower()) == 'nfce'
    pagamento = unicodedata.normalize('NFKD', dados.get('forma_pagamento') or '')
    pagamento = pagamento.encode('ascii', 'ignore').decode().lower()
    assert 'credito' in pagamento

    esperados = {
        # Código: quantidade, unidade, preço unitário, desconto, total líquido.
        '7892840824143': (1, 'UN', 19.99, 0, 19.99),
        '7892840825201': (2, 'UN', 29.59, 0, 59.18),
        '7891962079585': (2, 'UN', 7.99, 2, 13.98),
        '7891962056678': (2, 'UN', 7.99, 2, 13.98),
        '1050': (0.224, 'KG', 59.90, 0, 13.42),
        '1039': (0.380, 'KG', 89.90, 0, 34.16),
        '7892840813444': (1, 'UN', 7.98, 1.80, 6.18),
        '7892840812874': (1, 'UN', 8.99, 1.50, 7.49),
        '7894900025019': (1, 'UN', 2.89, 0, 2.89),
        '7891095100729': (2, 'UN', 3.89, 2.20, 5.58),
        '7891095912353': (2, 'UN', 5.39, 0, 10.78),
    }
    itens = dados.get('itens') or []
    assert len(itens) == len(esperados)
    por_codigo = {item.get('codigo'): item for item in itens}
    assert por_codigo.keys() == esperados.keys()
    for codigo, (quantidade, unidade, preco, desconto, total) in esperados.items():
        item = por_codigo[codigo]
        assert item.get('descricao'), codigo
        assert item.get('quantidade') == pytest.approx(quantidade, abs=0.00001), codigo
        assert (item.get('unidade') or '').upper() == unidade, codigo
        assert item.get('preco_unitario') == pytest.approx(preco, abs=0.001), codigo
        assert item.get('desconto') == pytest.approx(desconto, abs=0.001), codigo
        assert item.get('preco_total') == pytest.approx(total, abs=0.001), codigo
