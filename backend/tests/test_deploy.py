"""Testes sem daemon Docker, GPU, downloads ou dependências Python adicionais."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import deploy
from scripts import ollama as probe


NVIDIA = deploy.Hardware('nvidia', 'NVIDIA teste', 'GPU-1234-abcd')
IGPU = deploy.Hardware('vulkan', 'Intel integrada', '/dev/dri/renderD128', True)
CONFIG = {'services': {
    'app': {'environment': {'OLLAMA_URL': 'http://llm:11434', 'OLLAMA_NUM_CTX': '2048', 'OLLAMA_TIMEOUT': '120'}},
}}


def completed(code=0, output=''):
    return subprocess.CompletedProcess([], code, stdout=output)


class HardwareTests(unittest.TestCase):
    def test_nvidia_usa_uuid_e_ignora_saida_invalida(self):
        self.assertEqual(deploy.nvidia_devices('GPU-1234-abcd, NVIDIA teste\nsem GPU\n'), [NVIDIA])

    def test_vulkan_prioriza_dedicada_e_ignora_cpu_e_duplicatas(self):
        saida = '''GPU0:
 deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
 deviceName = Intel integrada
 vendorID = 0x8086
 hasRender = true
 drmRenderMinor = 128
GPU1:
 deviceType = PHYSICAL_DEVICE_TYPE_CPU
 deviceName = llvmpipe
GPU2:
 deviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
 deviceName = AMD dedicada
 vendorID = 0x1002
 hasRender = true
 drmRenderMinor = 129
GPU3:
 deviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
 deviceName = AMD outro driver
 vendorID = 0x1002
 hasRender = true
 drmRenderMinor = 129
'''
        with patch.object(Path, 'is_char_device', return_value=True):
            gpus = deploy.vulkan_devices(saida)
        self.assertEqual([g.nome for g in gpus], ['AMD dedicada', 'Intel integrada'])
        self.assertEqual(gpus[-1], IGPU)

    def test_vulkan_nao_adivinha_tipo_ou_dispositivo(self):
        with patch.object(Path, 'is_char_device', return_value=False):
            self.assertEqual(deploy.vulkan_devices('GPU0:\n deviceType = INTEGRATED_GPU\n vendorID = 0x8086\n'), [])

    def test_daemon_remoto_nao_recebe_dispositivos_locais(self):
        with patch.dict('os.environ', {'DOCKER_HOST': 'ssh://servidor'}, clear=True), patch.object(deploy, 'inspect_host') as inspect:
            self.assertEqual(deploy.discover({}), [deploy.CPU])
            inspect.assert_not_called()

    def test_configuracao_expoe_uma_gpu_e_cpu_desabilita_aceleracao(self):
        vulkan = IGPU.compose_settings()
        self.assertEqual(vulkan['devices'], ['/dev/dri/renderD128:/dev/dri/renderD128'])
        self.assertNotIn('GGML_VK_VISIBLE_DEVICES', vulkan['environment'])
        cpu = deploy.CPU.compose_settings()
        self.assertNotIn('devices', cpu)
        self.assertEqual(cpu['environment']['OLLAMA_VULKAN'], '0')


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'docker-compose.yml'
        self.original = deploy.COMPOSE_FILE.read_text()
        self.path.write_text(self.original)
        compose_file = patch.object(deploy, 'COMPOSE_FILE', self.path)
        compose_file.start()
        self.addCleanup(compose_file.stop)

    def test_gpu_falha_igpu_aprovada_cpu_nao_testada(self):
        with patch.object(deploy, 'run', side_effect=[completed(), completed(10), completed(), completed()]) as run:
            escolhido = deploy.select_hardware([NVIDIA, IGPU, deploy.CPU])
        self.assertEqual(escolhido, IGPU)
        self.assertEqual(run.call_count, 4)
        self.assertIn('/dev/dri/renderD128', self.path.read_text())
        self.assertNotIn('GPU-1234-abcd', self.path.read_text())
        self.assertIn('OLLAMA_GPU_MODE=vulkan', run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-4:], ['app', '-m', 'scripts.ollama', 'testar'])

    def test_runtime_nvidia_ausente_tenta_cpu(self):
        # Início NVIDIA falha, daemon acessível, início CPU e teste funcionam.
        with patch.object(deploy, 'run', side_effect=[completed(1), completed(), completed(), completed()]):
            self.assertEqual(deploy.select_hardware([NVIDIA, deploy.CPU]), deploy.CPU)

    def test_erro_fatal_nao_provoca_fallback(self):
        with patch.object(deploy, 'run', side_effect=[completed(), completed(20)]) as run:
            with self.assertRaises(deploy.DeployError):
                deploy.select_hardware([NVIDIA, deploy.CPU])
        self.assertEqual(run.call_count, 2)

    def test_falha_cpu_nao_anuncia_sucesso(self):
        with patch.object(deploy, 'run', side_effect=[completed(), completed(10)]):
            with self.assertRaisesRegex(deploy.DeployError, 'CPU'):
                deploy.select_hardware([deploy.CPU])

    def test_preparacao_falha_antes_de_tentar_gpu(self):
        respostas = [completed(), completed(output='{"OSType":"linux"}'), completed(output=json.dumps(CONFIG)), completed(), completed(), completed(1)]
        with patch.object(deploy, 'STATE', Path(self.temp.name)), patch.object(deploy, 'run', side_effect=respostas), patch.object(deploy, 'select_hardware') as select:
            with self.assertRaisesRegex(deploy.DeployError, 'etapa de preparação'):
                deploy.deploy(True)
        select.assert_not_called()
        self.assertEqual(self.path.read_text(), self.original)
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))

    def test_deploy_edita_unico_compose_e_permite_pull_do_banco_no_primeiro_uso(self):
        def command(args, **kwargs):
            if args[:2] == ['docker', 'info']:
                return completed(output='{"OSType":"linux"}')
            if 'config' in args:
                return completed(output=json.dumps(CONFIG))
            return completed()
        (Path(self.temp.name) / 'compose.hardware.json').write_text('{}')
        with patch.object(deploy, 'STATE', Path(self.temp.name)), patch.object(deploy, 'run', side_effect=command) as run, patch.object(deploy, 'discover', return_value=[NVIDIA]):
            deploy.deploy(False)
        self.assertIn('GPU-1234-abcd', self.path.read_text())
        self.assertFalse((Path(self.temp.name) / 'compose.hardware.json').exists())
        ultimo = run.call_args.args[0]
        self.assertIn(str(self.path), ultimo)
        self.assertIn('--wait', ultimo)
        self.assertNotIn('--pull', ultimo)
        comandos = [call.args[0] for call in run.call_args_list]
        self.assertIn(deploy.compose() + ['build', 'app'], comandos)
        for cmd in comandos:
            if cmd[:2] == ['docker', 'compose'] and 'version' not in cmd:
                self.assertEqual(cmd.count('-f'), 1)
                self.assertIn(str(self.path), cmd)
        auxiliares = [cmd for cmd in comandos if 'run' in cmd]
        self.assertEqual([cmd[-4:] for cmd in auxiliares], [
            ['app', '-m', 'scripts.ollama', 'preparar'],
            ['app', '-m', 'scripts.ollama', 'testar'],
        ])
        for cmd in auxiliares:
            self.assertIn('--rm', cmd)
            self.assertIn('--no-deps', cmd)
        self.assertTrue(all('preparacao' not in cmd for cmd in comandos))

    def test_alternar_hardware_preserva_conteudo_externo_e_remove_gpu_anterior(self):
        personalizado = deploy.render_hardware(self.original, deploy.CPU).replace('OLLAMA_MAX_QUEUE: "1"', 'OLLAMA_MAX_QUEUE: "5"')
        self.path.write_text(personalizado)
        deploy.configure_hardware(NVIDIA)
        self.assertIn('GPU-1234-abcd', self.path.read_text())
        deploy.configure_hardware(IGPU)
        self.assertIn('/dev/dri/renderD128', self.path.read_text())
        self.assertNotIn('GPU-1234-abcd', self.path.read_text())
        deploy.configure_hardware(deploy.CPU)
        self.assertEqual(self.path.read_text(), personalizado)
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))

    def test_marcadores_invalidos_nao_alteram_arquivo(self):
        for source in (self.original.replace('# BEGIN DEPLOY GPU ENV', '# removido'), self.original + '      # END DEPLOY GPU ENV\n'):
            self.path.write_text(source)
            with self.assertRaises(deploy.DeployError):
                deploy.configure_hardware(NVIDIA)
            self.assertEqual(self.path.read_text(), source)

    def test_falha_de_escrita_atomica_preserva_arquivo(self):
        with patch.object(Path, 'replace', side_effect=OSError('disco indisponível')):
            with self.assertRaises(OSError):
                deploy.configure_hardware(NVIDIA)
        self.assertEqual(self.path.read_text(), self.original)
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))

    def test_erro_no_up_final_preserva_hardware_ja_validado(self):
        def command(args, **kwargs):
            if args[:2] == ['docker', 'info']:
                return completed(output='{"OSType":"linux"}')
            if 'config' in args:
                return completed(output=json.dumps(CONFIG))
            return completed(1 if '--wait' in args else 0)
        with patch.object(deploy, 'run', side_effect=command), patch.object(deploy, 'discover', return_value=[NVIDIA]):
            with self.assertRaisesRegex(deploy.DeployError, 'Hardware validado'):
                deploy.deploy(False)
        self.assertIn('GPU-1234-abcd', self.path.read_text())

    def test_ollama_externo_rejeitado_antes_de_mutacoes(self):
        config = {'services': {'app': {'environment': {'OLLAMA_URL': 'http://externo:11434'}}}}
        with patch.object(deploy, 'run', side_effect=[completed(), completed(output='{"OSType":"linux"}'), completed(output=json.dumps(config))]) as run:
            with self.assertRaisesRegex(deploy.DeployError, 'Ollama local'):
                deploy.deploy(True)
        self.assertEqual(run.call_count, 3)


class ComposeCliTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('docker'), 'Docker CLI não instalado')
    def test_comandos_auxiliares_aceitos_pelo_parser_real_do_compose(self):
        version = subprocess.run(['docker', 'compose', 'version'], capture_output=True, text=True, timeout=15)
        if version.returncode:
            self.skipTest('Plugin Docker Compose não disponível')
        for acao in ('preparar', 'testar'):
            with self.subTest(acao=acao):
                comando = deploy.ollama_task(acao)
                # --help valida as opções sem acessar o daemon ou iniciar containers.
                comando.insert(comando.index('app'), '--help')
                resultado = subprocess.run(comando, capture_output=True, text=True, timeout=15)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)
                self.assertIn('Usage:', resultado.stdout)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {'OLLAMA_MODEL': 'teste:latest', 'OLLAMA_GPU_MODE': 'vulkan'})
        env.start()
        self.addCleanup(env.stop)
        ready = patch.object(probe, 'aguardar_ollama', return_value=[{'name': 'teste:latest'}])
        ready.start()
        self.addCleanup(ready.stop)

    def inference(self, vram):
        return [io.BytesIO(b'{"done":true,"eval_count":8}'), io.BytesIO(json.dumps({'models': [{'name': 'teste:latest', 'size_vram': vram}]}).encode())]

    def test_gpu_precisa_de_inferencia_e_vram_positiva(self):
        with patch.object(probe, 'urlopen', side_effect=self.inference(1024)):
            self.assertEqual(probe.testar(), 0)
        with patch.object(probe, 'urlopen', side_effect=self.inference(0)):
            self.assertEqual(probe.testar(), 10)

    def test_cpu_aprovada_sem_vram(self):
        with patch.dict('os.environ', {'OLLAMA_GPU_MODE': 'cpu'}), patch.object(probe, 'urlopen', side_effect=self.inference(0)):
            self.assertEqual(probe.testar(), 0)

    def test_falta_ram_fatal_mas_erro_driver_permite_proximo(self):
        for detalhe, esperado in [('model requires more system memory', 20), ('CUDA error', 10)]:
            erro = HTTPError('http://llm', 500, '', {}, io.BytesIO(detalhe.encode()))
            with patch.object(probe, 'urlopen', side_effect=erro):
                self.assertEqual(probe.testar(), esperado)

    def test_resposta_sem_tokens_nao_valida_gpu(self):
        with patch.object(probe, 'urlopen', return_value=io.BytesIO(b'{"done":true,"eval_count":0}')):
            self.assertEqual(probe.testar(), 10)

    def test_comando_preparar_garante_modelo_antes_de_testar(self):
        with patch.object(probe, 'diagnosticar_container', return_value={}), patch.object(probe, 'garantir_modelo') as garantir, patch.object(probe, 'testar') as testar:
            self.assertEqual(probe.main('preparar'), 0)
        garantir.assert_called_once()
        self.assertEqual(garantir.call_args.args[1], 'teste:latest')
        testar.assert_not_called()

    def test_comando_testar_preserva_codigo_de_fallback(self):
        with patch.object(probe, 'testar', return_value=10), patch.object(probe, 'preparar') as preparar:
            self.assertEqual(probe.main('testar'), 10)
        preparar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
