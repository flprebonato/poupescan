"""Deploy local: NVIDIA/CUDA ou GPU dedicada Vulkan, integrada Vulkan, CPU.

Somente biblioteca padrão. O Compose resolve .env; nunca fazemos source dele.
"""
import argparse
import csv
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.deploy'
COMPOSE_FILE = ROOT / 'docker-compose.yml'


class DeployError(Exception):
    pass


def log(mensagem: str) -> None:
    print(f'[deploy] {mensagem}', flush=True)


def run(args: list[str], *, capture: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=capture, timeout=timeout, check=False)


def required(args: list[str], mensagem: str, *, capture: bool = False) -> str:
    resultado = run(args, capture=capture)
    if resultado.returncode:
        raise DeployError(mensagem)
    return resultado.stdout or ''


def inspect_host(args: list[str]) -> str:
    try:
        resultado = run(args, capture=True, timeout=30)
        return resultado.stdout if resultado.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


@dataclass(frozen=True)
class Hardware:
    modo: str
    nome: str
    dispositivo: str = ''
    integrada: bool = False

    def compose_settings(self) -> dict:
        ambiente = {'OLLAMA_VULKAN': '0', 'CUDA_VISIBLE_DEVICES': '-1', 'ROCR_VISIBLE_DEVICES': '-1'}
        ollama: dict = {'environment': ambiente}
        if self.modo == 'nvidia':
            ambiente['CUDA_VISIBLE_DEVICES'] = self.dispositivo
            ollama['deploy'] = {'resources': {'reservations': {'devices': [{
                'driver': 'nvidia', 'device_ids': [self.dispositivo], 'capabilities': ['gpu'],
            }]}}}
        elif self.modo == 'vulkan':
            ambiente['OLLAMA_VULKAN'] = '1'
            # Expõe somente o render node desta GPU: índices Vulkan do host e
            # container podem diferir, por isso não copiamos GGML_VK_VISIBLE_DEVICES.
            ollama['devices'] = [f'{self.dispositivo}:{self.dispositivo}']
        return ollama


CPU = Hardware('cpu', 'CPU e RAM')


def nvidia_devices(saida: str) -> list[Hardware]:
    dispositivos = []
    for linha in csv.reader(saida.splitlines()):
        if len(linha) == 2 and re.fullmatch(r'GPU-[a-fA-F0-9-]+', linha[0].strip()):
            dispositivos.append(Hardware('nvidia', linha[1].strip(), linha[0].strip()))
    return dispositivos


def vulkan_devices(saida: str) -> list[Hardware]:
    dispositivos = []
    vistos = set()
    for bloco in re.split(r'^\s*GPU\d+:\s*$', saida, flags=re.M)[1:]:
        campos = dict(re.findall(r'^\s*(deviceType|deviceName|vendorID|hasRender|drmRenderMinor)\s*=\s*(.*?)\s*$', bloco, re.M))
        tipo = campos.get('deviceType', '')
        if not tipo.endswith(('DISCRETE_GPU', 'INTEGRATED_GPU')):
            continue  # Exclui llvmpipe e outros dispositivos de software.
        if campos.get('vendorID') not in ('0x8086', '0x1002'):
            continue  # NVIDIA usa o Container Toolkit, acima.
        minor = campos.get('drmRenderMinor', '')
        if campos.get('hasRender') != 'true' or not minor.isdecimal():
            log('GPU Vulkan sem render node identificável; ignorando ' + campos.get('deviceName', 'GPU') + '.')
            continue
        dispositivo = f'/dev/dri/renderD{int(minor)}'
        if dispositivo not in vistos and Path(dispositivo).is_char_device():
            dispositivos.append(Hardware('vulkan', campos.get('deviceName', dispositivo), dispositivo, tipo.endswith('INTEGRATED_GPU')))
            vistos.add(dispositivo)
    return sorted(dispositivos, key=lambda gpu: gpu.integrada)


def discover(info: dict) -> list[Hardware]:
    # Nunca cruza hardware do cliente com um daemon remoto.
    endpoint = os.environ.get('DOCKER_HOST', '')
    if os.environ.get('DOCKER_CONTEXT') or not endpoint:
        endpoint = inspect_host(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}']).strip()
    if not endpoint.startswith('unix://'):
        log('Daemon remoto/não local: seleção automática limitada à CPU; execute no host do Docker para detectar GPUs.')
        return [CPU]
    dispositivos = nvidia_devices(inspect_host(['nvidia-smi', '--query-gpu=uuid,name', '--format=csv,noheader']))
    linux_local = platform.system() == 'Linux' and 'docker desktop' not in info.get('OperatingSystem', '').lower()
    if linux_local and Path('/dev/dri').exists():
        if shutil.which('vulkaninfo'):
            saida = inspect_host(['vulkaninfo'])
            vulkan = vulkan_devices(saida)
            if not vulkan:
                log('Nenhuma GPU Intel/AMD com Vulkan e render node foi identificada.')
            dispositivos.extend(vulkan)
        else:
            log('Instale vulkan-tools (vulkaninfo) e os drivers Vulkan para detectar GPUs Intel/AMD; seguindo com as opções disponíveis.')
    return dispositivos + [CPU]


def yaml_mapping(dados: dict, indent: int) -> str:
    linhas = []
    for chave, valor in dados.items():
        prefixo = ' ' * indent + chave + ':'
        if isinstance(valor, dict):
            linhas.extend([prefixo, yaml_mapping(valor, indent + 2).rstrip('\n')])
        else:
            # Valores JSON também são YAML válido, inclusive listas e strings.
            linhas.append(prefixo + ' ' + json.dumps(valor, ensure_ascii=False))
    return '\n'.join(linhas) + '\n'


def render_hardware(source: str, hardware: Hardware) -> str:
    settings = hardware.compose_settings()
    ambiente = settings.pop('environment')
    for nome, conteudo, indent in (
        ('GPU ENV', yaml_mapping(ambiente, 6), 6),
        ('GPU DEVICES', yaml_mapping(settings, 4) if settings else '    # CPU: nenhum dispositivo de GPU solicitado.\n', 4),
    ):
        inicio = ' ' * indent + f'# BEGIN DEPLOY {nome}\n'
        fim = ' ' * indent + f'# END DEPLOY {nome}\n'
        if source.count(inicio) != 1 or source.count(fim) != 1:
            raise DeployError('Marcadores de hardware ausentes ou duplicados em docker-compose.yml.')
        antes, restante = source.split(inicio)
        if fim not in restante:
            raise DeployError('Marcadores de hardware fora de ordem em docker-compose.yml.')
        _, depois = restante.split(fim)
        source = antes + inicio + conteudo + fim + depois
    return source


def write_compose(source: str) -> None:
    # Substituição atômica: nunca deixa o arquivo parcialmente escrito.
    fd, nome = tempfile.mkstemp(prefix='.docker-compose-', suffix='.tmp', dir=COMPOSE_FILE.parent)
    temporario = Path(nome)
    try:
        with os.fdopen(fd, 'w') as arquivo:
            arquivo.write(source)
        temporario.chmod(COMPOSE_FILE.stat().st_mode & 0o777)
        temporario.replace(COMPOSE_FILE)
    finally:
        temporario.unlink(missing_ok=True)


def configure_hardware(hardware: Hardware) -> None:
    write_compose(render_hardware(COMPOSE_FILE.read_text(), hardware))


def compose() -> list[str]:
    return ['docker', 'compose', '--project-directory', str(ROOT), '-f', str(COMPOSE_FILE)]


def ollama_task(acao: str, modo: str = 'cpu') -> list[str]:
    # Reutiliza a imagem e a rede da app, sem iniciar API, banco ou dependências.
    # O container temporário herda as variáveis OLLAMA_* resolvidas pelo Compose.
    # A imagem já foi construída pelo deploy; run não aceita --no-build.
    return compose() + [
        'run', '--rm', '-T', '--no-deps', '--pull', 'never',
        '-e', f'OLLAMA_GPU_MODE={modo}', 'app', '-m', 'scripts.ollama', acao,
    ]


def select_hardware(candidatos: list[Hardware]) -> Hardware:
    for hardware in candidatos:
        log(f'Testando {hardware.nome} ({hardware.modo}' + (', integrada' if hardware.integrada else '') + ')...')
        configure_hardware(hardware)
        comando = compose()
        inicio = run(comando + ['up', '-d', '--no-deps', '--force-recreate', 'llm'])
        if inicio.returncode:
            required(['docker', 'info'], 'O daemon Docker ficou indisponível.', capture=True)
            if hardware.modo == 'cpu':
                raise DeployError('Não foi possível iniciar o Ollama nem em CPU.')
            log('O Docker não iniciou o Ollama com este dispositivo; tentando o próximo.')
            continue
        teste = run(ollama_task('testar', hardware.modo))
        if teste.returncode == 0:
            return hardware
        if teste.returncode != 10:
            raise DeployError('Validação interrompida por erro de modelo, memória ou execução do teste. Consulte os logs acima.')
        if hardware.modo == 'cpu':
            raise DeployError('O modelo falhou também em CPU. Confira RAM disponível e docker compose logs llm.')
        log('Aceleração não validada; tentando o próximo dispositivo.')
    raise DeployError('Nenhuma configuração validada.')


def deploy(cpu_only: bool) -> None:
    required(['docker', 'compose', 'version'], 'Instale o plugin Docker Compose.')
    info = json.loads(required(['docker', 'info', '--format', '{{json .}}'], 'Docker indisponível: verifique o daemon e as permissões do usuário.', capture=True))
    if info.get('OSType') != 'linux':
        raise DeployError('Este projeto requer containers Linux.')
    config = json.loads(required(compose() + ['config', '--format', 'json'], 'Configuração Compose inválida. Execute docker compose config para diagnosticar.', capture=True))
    url = config['services']['app']['environment'].get('OLLAMA_URL', '').rstrip('/')
    if url != 'http://llm:11434':
        raise DeployError('deploy.sh gerencia o Ollama local. Configure OLLAMA_URL=http://llm:11434 ou use o Compose manual para um servidor externo.')
    candidatos = [CPU] if cpu_only else discover(info)
    log('Ordem das tentativas: ' + ' → '.join(g.nome for g in candidatos))
    original = COMPOSE_FILE.read_text()
    render_hardware(original, CPU)  # Verifica os marcadores antes de qualquer mudança.
    required(compose() + ['build', 'app'], 'Falha ao construir a imagem da aplicação; nenhum fallback de GPU foi iniciado.')

    validado = False
    try:
        configure_hardware(CPU)
        comando = compose()
        # A preparação em CPU separa problemas de download das tentativas de GPU.
        log('Preparando o modelo no volume persistente (a primeira execução pode demorar)...')
        required(comando + ['up', '-d', '--no-deps', '--force-recreate', 'llm'], 'Falha ao iniciar Ollama para preparação.')
        required(ollama_task('preparar'), 'Falha na etapa de preparação. Confira o erro acima e execute ./deploy.sh novamente.')
        escolhido = select_hardware(candidatos)
        validado = True
        required(compose() + ['up', '-d', '--no-build', '--wait'], 'Hardware validado, mas a aplicação/banco não iniciou. Confira docker compose logs.')
        # Remove apenas o artefato obsoleto de versões anteriores do deploy.
        (STATE / 'compose.hardware.json').unlink(missing_ok=True)
        log(f'Deploy concluído com {escolhido.nome}. Aplicação: http://localhost:8000')
        log('Hardware configurado em docker-compose.yml. Para manutenção: docker compose ps')
    finally:
        if not validado:
            write_compose(original)
            log('Configuração original de docker-compose.yml restaurada; os containers não foram revertidos.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', action='store_true', help='Força CPU e RAM, sem tentar GPUs.')
    args = parser.parse_args()
    STATE.mkdir(exist_ok=True)
    try:
        with (STATE / 'deploy.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DeployError('Já existe um deploy em andamento neste diretório.') from None
            deploy(args.cpu)
    except (DeployError, OSError, ValueError, KeyError) as erro:
        log(f'ERRO: {erro}')
        return 1
    except KeyboardInterrupt:
        log('Deploy interrompido. Execute ./deploy.sh para tentar novamente.')
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
