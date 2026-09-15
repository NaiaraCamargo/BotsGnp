import errno
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from pncp_shared.api import cliente_pncp


def resposta(status):
    retorno = Mock(status_code=status, headers={})
    retorno.close = Mock()
    return retorno


class ClientePncpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arquivo_lock = patch.object(cliente_pncp, "_arquivo_lock", f"{self.tmp.name}/pncp.lock")
        self.intervalo = patch.object(cliente_pncp, "INTERVALO_MINIMO_SEG", 0)
        self.arquivo_lock.start()
        self.intervalo.start()

    def tearDown(self):
        self.intervalo.stop()
        self.arquivo_lock.stop()
        self.tmp.cleanup()

    def test_realiza_tres_tentativas_com_espera_progressiva_global(self):
        respostas = [resposta(500), resposta(503), resposta(200)]
        agora = [1000.0]

        def dormir(segundos):
            agora[0] += segundos

        with patch.object(cliente_pncp.requests, "request", side_effect=respostas) as request, \
             patch.object(cliente_pncp.time, "time", side_effect=lambda: agora[0]), \
             patch.object(cliente_pncp.time, "sleep", side_effect=dormir) as sleep:
            retorno = cliente_pncp.requisicao_pncp("GET", "https://pncp.gov.br/api/teste")

        self.assertIs(retorno, respostas[2])
        self.assertEqual(request.call_count, 3)
        self.assertEqual(len(sleep.call_args_list), 2)
        self.assertGreaterEqual(sleep.call_args_list[0].args[0], 9)
        self.assertGreaterEqual(sleep.call_args_list[1].args[0], 19)

    def test_429_publica_bloqueio_global_de_quarenta_segundos(self):
        respostas = [resposta(429), resposta(200)]
        agora = [1000.0]

        def dormir(segundos):
            agora[0] += segundos

        with patch.object(cliente_pncp.requests, "request", side_effect=respostas), \
             patch.object(cliente_pncp.time, "time", side_effect=lambda: agora[0]), \
             patch.object(cliente_pncp.time, "sleep", side_effect=dormir) as sleep:
            retorno = cliente_pncp.requisicao_pncp("GET", "https://pncp.gov.br/api/teste", max_tentativas=2)

        self.assertIs(retorno, respostas[1])
        self.assertGreaterEqual(sleep.call_args_list[0].args[0], 39)

    def test_le_estado_antigo_salvo_como_timestamp(self):
        with open(cliente_pncp._arquivo_lock, "w", encoding="utf-8") as arquivo:
            arquivo.write("123.5")

        with open(cliente_pncp._arquivo_lock, "rb") as arquivo:
            estado = cliente_pncp._ler_estado(arquivo)

        self.assertEqual(estado, {"ultima_chamada": 123.5, "bloqueado_ate": 0})

    def test_navegacao_lenta_nao_bloqueia_requisicao_liberada_pelo_limitador(self):
        navegacao_iniciada = threading.Event()
        liberar_navegacao = threading.Event()

        def navegar():
            navegacao_iniciada.set()
            liberar_navegacao.wait(2)

        with patch.object(cliente_pncp.requests, "request", return_value=resposta(200)) as request:
            thread_navegacao = threading.Thread(target=cliente_pncp.executar_navegacao_pncp, args=(navegar,))
            thread_requisicao = threading.Thread(target=cliente_pncp.requisicao_pncp, args=("GET", "https://pncp.gov.br/api/teste"), kwargs={"max_tentativas": 1})
            thread_navegacao.start()
            self.assertTrue(navegacao_iniciada.wait(1))
            thread_requisicao.start()
            thread_requisicao.join(1)
            self.assertFalse(thread_requisicao.is_alive())
            self.assertTrue(thread_navegacao.is_alive())
            request.assert_called_once()
            liberar_navegacao.set()
            thread_navegacao.join(1)

    def test_inicios_sao_espacados_sem_manter_lock_durante_a_operacao(self):
        agora = [1000.0]

        def dormir(segundos):
            agora[0] += segundos

        with patch.object(cliente_pncp, "INTERVALO_MINIMO_SEG", 3.1), \
             patch.object(cliente_pncp.time, "time", side_effect=lambda: agora[0]), \
             patch.object(cliente_pncp.time, "sleep", side_effect=dormir) as sleep:
            cliente_pncp.executar_navegacao_pncp(lambda: None)
            cliente_pncp.executar_navegacao_pncp(lambda: None)

        sleep.assert_called_once_with(3.1)

    def test_request_e_navegacao_executam_sem_manter_lock_local(self):
        def verificar_request(*args, **kwargs):
            self.assertFalse(cliente_pncp._lock_thread.locked())
            return resposta(200)

        with patch.object(cliente_pncp.requests, "request", side_effect=verificar_request):
            cliente_pncp.requisicao_pncp("GET", "https://pncp.gov.br/api/teste", max_tentativas=1)

        cliente_pncp.executar_navegacao_pncp(lambda: self.assertFalse(cliente_pncp._lock_thread.locked()))

    def test_cooldown_preserva_inicio_mais_recente_de_outro_bot(self):
        with open(cliente_pncp._arquivo_lock, "w", encoding="utf-8") as arquivo:
            json.dump({"ultima_chamada": 1500.0, "bloqueado_ate": 0}, arquivo)

        with patch.object(cliente_pncp.time, "time", return_value=1000.0):
            cliente_pncp._publicar_bloqueio_global(40)

        with open(cliente_pncp._arquivo_lock, "r", encoding="utf-8") as arquivo:
            estado = json.load(arquivo)

        self.assertEqual(estado["ultima_chamada"], 1500.0)
        self.assertEqual(estado["bloqueado_ate"], 1040.0)

    def test_lock_windows_aguarda_erro_de_deadlock_e_tenta_novamente(self):
        arquivo = Mock()
        arquivo.fileno.return_value = 10
        msvcrt = Mock(LK_NBLCK=2)
        msvcrt.locking.side_effect = [OSError(errno.EDEADLK, "Resource deadlock avoided") for _ in range(12)] + [None]

        with patch.object(cliente_pncp.os, "name", "nt"), patch.dict(sys.modules, {"msvcrt": msvcrt}), \
             patch.object(cliente_pncp.time, "sleep") as sleep:
            cliente_pncp._bloquear_arquivo(arquivo)

        self.assertEqual(msvcrt.locking.call_count, 13)
        self.assertEqual(sleep.call_count, 12)
        self.assertTrue(all(chamada.args == (cliente_pncp.INTERVALO_ESPERA_LOCK_SEG,) for chamada in sleep.call_args_list))

    def test_lock_windows_nao_oculta_erro_que_nao_seja_contencao(self):
        arquivo = Mock()
        arquivo.fileno.return_value = 10
        msvcrt = Mock(LK_NBLCK=2)
        msvcrt.locking.side_effect = OSError(errno.EBADF, "Bad file descriptor")

        with patch.object(cliente_pncp.os, "name", "nt"), patch.dict(sys.modules, {"msvcrt": msvcrt}), \
             self.assertRaises(OSError):
            cliente_pncp._bloquear_arquivo(arquivo)

    def test_arquivo_e_desbloqueado_quando_operacao_falha(self):
        with patch.object(cliente_pncp, "_bloquear_arquivo"), patch.object(cliente_pncp, "_desbloquear_arquivo") as desbloquear, \
             self.assertRaises(RuntimeError):
            with cliente_pncp._abrir_arquivo_bloqueado():
                raise RuntimeError("falha simulada")

        desbloquear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
