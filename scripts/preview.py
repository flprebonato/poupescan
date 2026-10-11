#!/usr/bin/env python3
"""Diagnóstico local, somente leitura, antes de implantar o PoupeScan.

Requer apenas Python 3.12+. Não instala drivers nem inicia containers.
Uso: python scripts/preview.py [--json]
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

MODELO = 'qwen3-vl:4b-instruct-q4_K_M'


def executar(comando: list[str]) -> str | None:
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return resultado.stdout.strip() if resultado.returncode == 0 else None


def hardware_windows() -> dict:
    powershell = shutil.which('powershell') or shutil.which('pwsh')
    if not powershell:
        return {'ram_gb': None, 'gpus': []}
    comando = """$ErrorActionPreference = 'Stop';
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;
$pc = Get-CimInstance Win32_ComputerSystem;
$gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name });
[PSCustomObject]@{ ram_bytes = $pc.TotalPhysicalMemory; gpus = $gpus } | ConvertTo-Json -Compress
"""
    saida = executar([powershell, '-NoProfile', '-NonInteractive', '-Command', comando])
    try:
        dados = json.loads(saida or '{}')
        gpus = dados.get('gpus') or []
        return {'ram_gb': round(int(dados['ram_bytes']) / 1024**3, 1), 'gpus': [gpus] if isinstance(gpus, str) else gpus}
    except (ValueError, KeyError, TypeError):
        return {'ram_gb': None, 'gpus': []}


def hardware_linux() -> dict:
    try:
        memoria = Path('/proc/meminfo').read_text()
        ram = round(int(re.search(r'^MemTotal:\s+(\d+)', memoria, re.M)[1]) / 1024**2, 1)
    except (OSError, TypeError, ValueError):
        ram = None
    pci = executar(['lspci', '-nn']) or ''
    gpus = [linha.strip() for linha in pci.splitlines() if re.search(r'VGA compatible controller|3D controller|Display controller', linha, re.I)]
    if not gpus:
        fabricantes = {'0x8086': 'Intel', '0x1002': 'AMD', '0x10de': 'NVIDIA'}
        for card in Path('/sys/class/drm').glob('card*'):
            if not re.fullmatch(r'card\d+', card.name):
                continue
            try:
                vendor = (card / 'device/vendor').read_text().strip()
                device = (card / 'device/device').read_text().strip()
                gpus.append(f'{fabricantes.get(vendor, vendor)} — dispositivo PCI {device}')
            except OSError:
                pass
    return {'ram_gb': ram, 'gpus': gpus}


def hardware_macos() -> dict:
    memoria = executar(['sysctl', '-n', 'hw.memsize'])
    saida = executar(['system_profiler', 'SPDisplaysDataType', '-json'])
    try:
        dados = json.loads(saida or '{}')
        gpus = [g.get('sppci_model', 'GPU Apple') for g in dados.get('SPDisplaysDataType', [])]
    except (ValueError, TypeError):
        gpus = []
    return {'ram_gb': round(int(memoria) / 1024**3, 1) if memoria and memoria.isdigit() else None, 'gpus': gpus}


def memoria_container(ram_gb: float | None, raiz: Path = Path('/sys/fs/cgroup')) -> float | None:
    """Considera limites cgroup v2/v1 em vez de anunciar toda a RAM do host."""
    valores = [ram_gb] if ram_gb is not None else []
    for relativo in ('memory.max', 'memory/memory.limit_in_bytes'):
        try:
            limite = int((raiz / relativo).read_text().strip())
            if 0 < limite < 2**60:  # v1 pode representar 'ilimitado' com um inteiro enorme.
                valores.append(limite / 1024**3)
        except (OSError, ValueError):
            pass
    return round(min(valores), 1) if valores else None


def diagnosticar_container() -> dict:
    hardware = hardware_linux()
    memoria = memoria_container(hardware['ram_gb'])
    modo = os.environ.get('OLLAMA_GPU_MODE', 'cpu')
    avisos = [
        'Este diagnóstico observa um container temporário da aplicação e a VM do Docker; não identifica necessariamente o sistema e toda a memória física do notebook.',
        'A detecção e o uso efetivo da GPU pertencem ao serviço Ollama; a presença de uma GPU em sysfs não comprova acesso pelo container.',
    ]
    if memoria is None or memoria < 6:
        avisos.append('Memória acessível limitada ou desconhecida. A leitura pode falhar por falta de memória; confira os recursos atribuídos ao Docker.')
    if modo == 'cpu':
        avisos.append('Configuração padrão sem passagem de GPU: leitura em CPU. A inicialização não altera os dispositivos definidos no Compose.')
    else:
        avisos.append(f'Aceleração solicitada: {modo}. Confirme o uso pelo Ollama durante a primeira leitura; não é possível garantir aceleração antes da inferência.')
    return {
        'ambiente': 'container Docker', 'sistema_do_container': platform.system(),
        'arquitetura': platform.machine(), 'ram_acessivel_gb': memoria,
        'gpus_visiveis_em_sysfs': hardware['gpus'], 'modo_configurado_ollama': modo,
        'modelo': os.environ.get('OLLAMA_MODEL', MODELO), 'avisos': avisos,
    }


def diagnosticar() -> dict:
    sistema = platform.system()
    detectar = {'Windows': hardware_windows, 'Linux': hardware_linux, 'Darwin': hardware_macos}.get(sistema)
    hardware = detectar() if detectar else {'ram_gb': None, 'gpus': []}
    docker_os = executar(['docker', 'info', '--format', '{{json .OperatingSystem}}'])
    endpoint = os.environ.get('DOCKER_HOST') or executar(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}']) or ''
    docker_local = endpoint.startswith('unix://') and bool(docker_os) and 'docker desktop' not in docker_os.lower()
    render = sorted(str(p) for p in Path('/dev/dri').glob('renderD*')) if sistema == 'Linux' else []
    # A API Vulkan precisa enxergar um dispositivo físico, não só llvmpipe/CPU.
    vulkan = (executar(['vulkaninfo', '--summary']) or '') if sistema == 'Linux' else ''
    vulkan_fisico = bool(re.search(r'deviceType\s*=.*(?:INTEGRATED_GPU|DISCRETE_GPU)', vulkan))
    intel_amd = any(re.search(r'\b(?:Intel|AMD|ATI|Radeon)\b', gpu, re.I) for gpu in hardware['gpus'])
    return recomendar({
        'sistema': sistema, 'arquitetura': platform.machine(), **hardware,
        'docker_disponivel': bool(docker_os), 'docker_linux_local': docker_local,
        'dispositivos_render': render, 'vulkan_gpu_detectada': vulkan_fisico,
        'gpu_intel_amd': intel_amd,
    })


def recomendar(dados: dict) -> dict:
    usar_igpu = (
        dados['sistema'] == 'Linux' and dados['docker_linux_local']
        and dados['dispositivos_render'] and dados['vulkan_gpu_detectada'] and dados['gpu_intel_amd']
    )
    perfil = 'vulkan' if usar_igpu else 'cpu'
    comando = './deploy.sh' if usar_igpu else './deploy.sh --cpu'
    avisos = []
    if dados['ram_gb'] is None:
        avisos.append('Não foi possível identificar a RAM; confirme a capacidade antes de iniciar.')
    elif dados['ram_gb'] < 6:
        avisos.append('Memória muito limitada para a demonstração; não há garantia de que o modelo caiba junto com o sistema e Docker.')
    elif dados['ram_gb'] < 12:
        avisos.append('Use um comprovante curto por vez e feche aplicativos pesados. A GPU integrada compartilha a RAM; ela não acrescenta memória ao notebook.')
    if not dados['docker_disponivel']:
        avisos.append('Docker não está disponível ou o usuário não tem acesso ao daemon. Inicie/configure o Docker antes de implantar.')
    if usar_igpu:
        avisos.append('GPU física acessível por Vulkan no host. O uso dentro do container ainda deve ser confirmado com ollama ps durante uma leitura; não há garantia de ganho de velocidade.')
    elif dados['sistema'] == 'Windows':
        avisos.append('Para manter tudo em Docker neste notebook, use CPU. A GPU integrada do Windows não é automaticamente disponibilizada pelo Docker Desktop; o deploy só tentará NVIDIA se detectar uma GPU compatível.')
    elif dados['sistema'] == 'Linux':
        avisos.append('Aceleração Intel/AMD não confirmada. O perfil CPU funciona sem expor dispositivos. Para avaliar Vulkan, verifique os drivers, vulkaninfo --summary, /dev/dri e um Docker Engine local.')
    else:
        avisos.append('A configuração portátil em Docker usa CPU. A detecção de GPU integrada pelo deploy foi preparada somente para Linux.')
    return {**dados, 'modelo': MODELO, 'perfil_recomendado': perfil, 'comando_iniciar': comando,
            'comando_baixar_modelo': f'docker compose exec llm ollama pull {MODELO}',
            'comando_verificar_uso': 'docker compose exec llm ollama ps', 'avisos': avisos}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Emite o diagnóstico estruturado, sem alterar arquivos.')
    args = parser.parse_args()
    dados = diagnosticar()
    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return
    print(f"Sistema: {dados['sistema']} ({dados['arquitetura']})")
    print(f"RAM total reconhecida pelo sistema: {dados['ram_gb']} GB" if dados['ram_gb'] is not None else 'RAM: não identificada')
    print('GPU(s): ' + ('; '.join(dados['gpus']) or 'não identificada'))
    print('Docker: ' + ('acessível' if dados['docker_disponivel'] else 'indisponível'))
    print(f"Modelo: {dados['modelo']}")
    print(f"Perfil recomendado: {dados['perfil_recomendado'].upper()}")
    for aviso in dados['avisos']:
        print(f'- {aviso}')
    print('\nComandos para usar depois de revisar o diagnóstico (não executados):')
    for campo in ('comando_iniciar', 'comando_baixar_modelo', 'comando_verificar_uso'):
        print(dados[campo])


if __name__ == '__main__':
    main()
