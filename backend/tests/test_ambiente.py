from scripts import preview as ambiente


def base(**alteracoes):
    return {
        'sistema': 'Linux', 'ram_gb': 8, 'gpus': ['Intel UHD Graphics'],
        'docker_disponivel': True, 'docker_linux_local': True,
        'dispositivos_render': ['/dev/dri/renderD128'], 'vulkan_gpu_detectada': True,
        'gpu_intel_amd': True, **alteracoes,
    }


def test_recomenda_vulkan_somente_com_deteccao_completa():
    resultado = ambiente.recomendar(base())
    assert resultado['perfil_recomendado'] == 'vulkan'
    assert resultado['comando_iniciar'] == './deploy.sh'
    for mudanca in ({'docker_linux_local': False}, {'dispositivos_render': []}, {'vulkan_gpu_detectada': False}, {'gpu_intel_amd': False}):
        resultado = ambiente.recomendar(base(**mudanca))
        assert resultado['perfil_recomendado'] == 'cpu'
        assert resultado['comando_iniciar'] == './deploy.sh --cpu'


def test_windows_nao_recomenda_dispositivo_linux():
    resultado = ambiente.recomendar(base(sistema='Windows'))
    assert resultado['perfil_recomendado'] == 'cpu'
    assert any('Docker Desktop' in aviso for aviso in resultado['avisos'])


def test_windows_consulta_ram_e_gpu_via_cim(monkeypatch):
    monkeypatch.setattr(ambiente.shutil, 'which', lambda _: 'powershell')
    monkeypatch.setattr(ambiente, 'executar', lambda _: '{"ram_bytes":8589934592,"gpus":["Intel Iris Xe Graphics"]}')
    assert ambiente.hardware_windows() == {'ram_gb': 8.0, 'gpus': ['Intel Iris Xe Graphics']}


def test_diagnostico_sem_docker_nao_instala_ou_inicia_servicos(monkeypatch):
    chamadas = []
    def executar(comando):
        chamadas.append(comando)
        return None
    monkeypatch.setattr(ambiente.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(ambiente, 'hardware_linux', lambda: {'ram_gb': 8, 'gpus': ['NVIDIA Corporation GeForce']})
    monkeypatch.setattr(ambiente, 'executar', executar)
    resultado = ambiente.diagnosticar()
    assert resultado['gpu_intel_amd'] is False
    assert resultado['docker_disponivel'] is False
    assert resultado['perfil_recomendado'] == 'cpu'
    assert all('up' not in cmd and 'run' not in cmd and 'install' not in cmd for cmd in chamadas)
