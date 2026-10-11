import io
import json
from urllib.error import URLError

import pytest

from scripts import ollama as preparo
from scripts import preview as ambiente


def test_memoria_respeita_cgroup_v2_e_v1(tmp_path):
    (tmp_path / 'memory.max').write_text(str(4 * 1024**3))
    assert ambiente.memoria_container(16, tmp_path) == 4
    (tmp_path / 'memory.max').write_text('max')
    assert ambiente.memoria_container(16, tmp_path) == 16
    (tmp_path / 'memory').mkdir()
    (tmp_path / 'memory/memory.limit_in_bytes').write_text(str(2 * 1024**3))
    assert ambiente.memoria_container(16, tmp_path) == 2
    assert ambiente.memoria_container(None, tmp_path) == 2


def test_container_nao_exige_docker_cli_ou_declara_gpu_utilizavel(monkeypatch):
    monkeypatch.setattr(ambiente, 'hardware_linux', lambda: {'ram_gb': 8, 'gpus': ['Intel UHD']})
    monkeypatch.setattr(ambiente, 'memoria_container', lambda _: 4)
    monkeypatch.setenv('OLLAMA_GPU_MODE', 'cpu')
    monkeypatch.setattr(ambiente, 'executar', lambda _: pytest.fail('Não deve chamar Docker CLI no container'))
    dados = ambiente.diagnosticar_container()
    assert dados['ram_acessivel_gb'] == 4
    assert dados['modo_configurado_ollama'] == 'cpu'
    assert dados['gpus_visiveis_em_sysfs'] == ['Intel UHD']


def test_modelo_existente_nao_baixa_novamente(monkeypatch):
    monkeypatch.setattr(preparo, 'urlopen', lambda *args, **kwargs: pytest.fail('Não deve baixar um modelo já disponível'))
    preparo.garantir_modelo('http://llm:11434', ambiente.MODELO, [{'name': ambiente.MODELO}])


def test_baixa_modelo_ausente_e_confirma_instalacao(monkeypatch):
    pedidos = []
    def abrir(pedido, **kwargs):
        pedidos.append(pedido)
        return io.BytesIO(b'{"status":"pulling manifest"}\n{"status":"success"}\n')
    monkeypatch.setattr(preparo, 'urlopen', abrir)
    monkeypatch.setattr(preparo, 'consultar_modelos', lambda _: [{'name': ambiente.MODELO}])
    preparo.garantir_modelo('http://llm:11434', ambiente.MODELO, [])
    assert pedidos[0].full_url == 'http://llm:11434/api/pull'
    assert json.loads(pedidos[0].data) == {'model': ambiente.MODELO, 'stream': True}


@pytest.mark.parametrize('conteudo', [b'{"error":"falha"}\n', b'{"status":"pulling manifest"}\n'])
def test_falha_ou_download_incompleto_bloqueia_preparacao(monkeypatch, conteudo):
    monkeypatch.setattr(preparo, 'urlopen', lambda *args, **kwargs: io.BytesIO(conteudo))
    with pytest.raises(RuntimeError):
        preparo.garantir_modelo('http://llm:11434', ambiente.MODELO, [])


def test_aguarda_ollama_e_limita_tempo(monkeypatch):
    chamadas = iter([URLError('ainda iniciando'), []])
    def consultar(_):
        valor = next(chamadas)
        if isinstance(valor, Exception):
            raise valor
        return valor
    monkeypatch.setattr(preparo, 'consultar_modelos', consultar)
    monkeypatch.setattr(preparo.time, 'sleep', lambda _: None)
    assert preparo.aguardar_ollama('http://llm:11434') == []
    def falhar(_):
        raise URLError('fora do ar')
    monkeypatch.setattr(preparo, 'consultar_modelos', falhar)
    with pytest.raises(RuntimeError, match='não ficou disponível'):
        preparo.aguardar_ollama('http://llm:11434', prazo=0)


def test_saida_nao_zero_quando_preparacao_falha(monkeypatch):
    def falhar():
        raise RuntimeError('Modelo indisponível')
    monkeypatch.setattr(preparo, 'preparar', falhar)
    assert preparo.main() == 1
