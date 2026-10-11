"""Download e inferência executados exclusivamente pelo deploy, na imagem da app."""
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.preview import diagnosticar_container


def consultar_modelos(url: str) -> list[dict]:
    with urlopen(f'{url}/api/tags', timeout=5) as resposta:
        return json.load(resposta)['models']


def aguardar_ollama(url: str, prazo: float = 120) -> list[dict]:
    limite = time.monotonic() + prazo
    print('[deploy] Aguardando o Ollama...', flush=True)
    while True:
        try:
            return consultar_modelos(url)
        except (URLError, OSError, ValueError, KeyError):
            if time.monotonic() >= limite:
                raise RuntimeError('O Ollama não ficou disponível. Verifique os logs do serviço llm e execute ./deploy.sh novamente.') from None
            time.sleep(2)


def modelo_presente(modelos: list[dict], nome: str) -> bool:
    nome_com_tag = nome if ':' in nome else f'{nome}:latest'
    return any(nome_com_tag in (m.get('name'), m.get('model')) for m in modelos)


def garantir_modelo(url: str, nome: str, modelos: list[dict]) -> None:
    if modelo_presente(modelos, nome):
        print(f'[deploy] Modelo {nome} já disponível no volume local.', flush=True)
        return
    print(f'[deploy] Baixando {nome}. O primeiro uso requer internet e pode levar alguns minutos.', flush=True)
    pedido = Request(f'{url}/api/pull', data=json.dumps({'model': nome, 'stream': True}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    sucesso = False
    ultimo = None
    with urlopen(pedido, timeout=120) as resposta:
        while linha := resposta.readline(64 * 1024):
            evento = json.loads(linha)
            if evento.get('error'):
                raise RuntimeError('O Ollama não conseguiu baixar o modelo. Confira o nome configurado, a conexão e o espaço em disco.')
            status = evento.get('status', '')
            if status == 'success':
                sucesso = True
            total = evento.get('total') or 0
            progresso = int(100 * evento.get('completed', 0) / total) // 10 * 10 if total else None
            marcador = (status, progresso)
            if marcador != ultimo:
                print(f'[deploy] {status}' + (f' — {progresso}%' if progresso is not None else ''), flush=True)
                ultimo = marcador
    if not sucesso or not modelo_presente(consultar_modelos(url), nome):
        raise RuntimeError('O download do modelo não foi concluído. Execute ./deploy.sh novamente para retomar.')


def preparar() -> None:
    dados = diagnosticar_container()
    print('[deploy] Diagnóstico automático do ambiente Docker:', flush=True)
    print(json.dumps(dados, ensure_ascii=False, indent=2), flush=True)
    url = os.environ.get('OLLAMA_URL', 'http://llm:11434').rstrip('/')
    modelo = os.environ.get('OLLAMA_MODEL', 'qwen3-vl:4b-instruct-q4_K_M')
    modelos = aguardar_ollama(url)
    garantir_modelo(url, modelo, modelos)
    print('[deploy] Diagnóstico concluído e modelo disponível para validar o hardware.', flush=True)


def testar() -> int:
    url = os.environ.get('OLLAMA_URL', 'http://llm:11434').rstrip('/')
    modelo = os.environ['OLLAMA_MODEL']
    gpu = os.environ.get('OLLAMA_GPU_MODE', 'cpu') != 'cpu'
    try:
        modelos = aguardar_ollama(url)
        if not modelo_presente(modelos, modelo):
            print('[deploy] Modelo ausente; execute a preparação novamente.', flush=True)
            return 20
        pedido = Request(
            f'{url}/api/chat',
            data=json.dumps({
                'model': modelo,
                'messages': [{'role': 'user', 'content': 'Responda apenas: OK'}],
                'stream': False, 'think': False, 'keep_alive': '2m',
                'options': {'num_predict': 8, 'num_ctx': int(os.environ.get('OLLAMA_NUM_CTX', '4096'))},
            }).encode(),
            headers={'Content-Type': 'application/json'}, method='POST',
        )
        with urlopen(pedido, timeout=float(os.environ.get('OLLAMA_TIMEOUT', '900'))) as resposta:
            resultado = json.load(resposta)
        if resultado.get('error') or not resultado.get('done') or not resultado.get('eval_count', 0):
            print('[deploy] O modelo não concluiu a inferência de teste.', flush=True)
            return 10
        with urlopen(f'{url}/api/ps', timeout=10) as resposta:
            carregados = json.load(resposta)['models']
        atual = next((m for m in carregados if modelo_presente([m], modelo)), None)
        if atual is None:
            print('[deploy] Não foi possível confirmar o modelo carregado.', flush=True)
            return 10
        acelerado = atual.get('size_vram', 0) > 0
        if gpu and not acelerado:
            print('[deploy] A inferência usou somente CPU; tentando o próximo dispositivo.', flush=True)
            return 10
        print('[deploy] Inferência validada: ' + ('GPU (total ou parcial).' if acelerado else 'CPU e RAM.'), flush=True)
        return 0
    except HTTPError as erro:
        detalhe = erro.read(8192).decode('utf-8', errors='replace').lower()
        # Falta de RAM, modelo inválido e erros de requisição não são falhas de driver.
        falta_ram = 'system memory' in detalhe or 'out of host memory' in detalhe
        if falta_ram or erro.code in (400, 401, 403, 404):
            print('[deploy] Falha no modelo/requisição ou RAM insuficiente. Confira os logs do Ollama.', flush=True)
            return 20
        print(f'[deploy] Ollama respondeu HTTP {erro.code} durante o teste; confira seus logs.', flush=True)
        return 10
    except (RuntimeError, URLError, OSError, ValueError, KeyError, TypeError):
        print('[deploy] Inferência indisponível, inválida ou fora do prazo; confira os logs do Ollama.', flush=True)
        return 10



def main(acao: str = 'preparar') -> int:
    if acao == 'testar':
        return testar()
    try:
        preparar()
    except (RuntimeError, HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as erro:
        # Não despeja URLs ou credenciais de configuração nos logs.
        mensagem = str(erro) if isinstance(erro, RuntimeError) else 'Falha na comunicação com o Ollama ou no download. Verifique rede, modelo e espaço em disco.'
        print(f'[deploy] ERRO: {mensagem}', file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acao', choices=('preparar', 'testar'))
    sys.exit(main(parser.parse_args().acao))
