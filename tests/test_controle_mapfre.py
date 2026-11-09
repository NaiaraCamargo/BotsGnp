import unittest
from contextlib import ExitStack
from threading import Barrier, Lock, get_ident
from unittest.mock import Mock, patch

from mapfre_downloader.controllers import controle_mapfre as controle


class ControleMapfreTest(unittest.TestCase):
    def executar_com_reservas(self, reservas, processar, quantidade=3, gravar=None, ciclos=1, logar=None):
        config = {"caminho_excel": "teste.xlsx", "links_simultaneos": quantidade, "tempo_de_login": 300, "tempo_recarregar_config": 900}
        drivers = [Mock(current_url="mapfre", window_handles=[str(numero)]) for numero in range(quantidade * ciclos)]
        for driver in drivers:
            driver.get_cookies.return_value = [{"name": "autenticacao", "value": "login-compartilhado", "domain": "mapfre"}]
        with ExitStack() as contexto:
            contexto.enter_context(patch.dict(controle.configuracoes, config, clear=True))
            for nome in ("limpar_console", "carregar_configuracoes", "controle_logs", "print", "logs"):
                contexto.enter_context(patch.object(controle, nome, create=True))
            contexto.enter_context(patch.object(controle, "ler_links_excel", return_value=reservas))
            contexto.enter_context(patch.object(controle, "criar_driver", side_effect=[(driver, str(i)) for i, driver in enumerate(drivers)]))
            login = contexto.enter_context(patch.object(controle, "processar_login_mafre", return_value=True, side_effect=logar))
            contexto.enter_context(patch.object(controle, "processar_reserva_arquivos", side_effect=processar))
            atualizar = contexto.enter_context(patch.object(controle, "atualizar_planilha", side_effect=gravar))
            finalizar = contexto.enter_context(patch.object(controle, "finalizar_driver"))
            fechar = contexto.enter_context(patch.object(controle, "fechar_planilha"))
            controle.executar_bot_mapfre()
        return atualizar, login, finalizar, fechar

    def test_processa_tres_em_paralelo_reutiliza_drivers_e_grava_no_coordenador(self):
        reservas = [{"reserva": str(i), "linha_excel": i + 1} for i in range(1, 8)]
        barreira = Barrier(3)
        lock = Lock()
        ativos = set()
        pico = 0
        processadas = []
        threads_gravacao = []

        def processar(driver, reserva):
            nonlocal pico
            with lock:
                self.assertNotIn(driver, ativos)
                ativos.add(driver)
                pico = max(pico, len(ativos))
                processadas.append(reserva["reserva"])
            try:
                if int(reserva["reserva"]) <= 3:
                    barreira.wait(timeout=5)
                return 1, 1, reserva["reserva"], "link", True, "OK"
            finally:
                with lock:
                    ativos.remove(driver)

        atualizar, login, finalizar, fechar = self.executar_com_reservas(reservas, processar, gravar=lambda *args, **kwargs: threads_gravacao.append(get_ident()))
        self.assertEqual(pico, 3)
        self.assertCountEqual(processadas, [reserva["reserva"] for reserva in reservas])
        self.assertEqual(set(threads_gravacao), {get_ident()})
        self.assertTrue(all(chamada.args[6] for chamada in atualizar.call_args_list))
        self.assertEqual(set(chamada.kwargs["linha_excel"] for chamada in atualizar.call_args_list), set(range(2, 9)))
        self.assertTrue(all(chamada.args[2] == chamada.args[5] for chamada in atualizar.call_args_list))
        login.assert_called_once()
        self.assertEqual(sum(chamada.args[0] is not None for chamada in finalizar.call_args_list), 3)
        fechar.assert_called_once()

    def test_reservas_repetidas_nao_rodam_juntas_e_todas_as_linhas_sao_gravadas(self):
        reservas = [{"reserva": reserva, "linha_excel": linha} for linha, reserva in enumerate(["1", "1", "2", "3", "1"], start=2)]
        barreira = Barrier(3)
        lock = Lock()
        ativos = set()

        def processar(driver, reserva):
            with lock:
                self.assertNotIn(reserva["reserva"], ativos)
                ativos.add(reserva["reserva"])
            try:
                if reserva["linha_excel"] in (2, 4, 5):
                    barreira.wait(timeout=5)
                return 0, 0, "", "", True, "OK"
            finally:
                with lock:
                    ativos.remove(reserva["reserva"])

        atualizar, _, _, _ = self.executar_com_reservas(reservas, processar)
        self.assertEqual(atualizar.call_count, 5)
        self.assertTrue(all(chamada.args[6] for chamada in atualizar.call_args_list))
        self.assertCountEqual([chamada.kwargs["linha_excel"] for chamada in atualizar.call_args_list], range(2, 7))

    def test_configuracao_um_processa_sequencialmente(self):
        processadas = []

        def processar(driver, reserva):
            processadas.append(reserva["reserva"])
            return 0, 0, "", "", True, "OK"

        atualizar, login, _, _ = self.executar_com_reservas([{"reserva": str(i)} for i in range(4)], processar, quantidade=1)
        self.assertEqual(processadas, [str(i) for i in range(4)])
        self.assertEqual(atualizar.call_count, 4)
        login.assert_called_once()

    def test_erro_em_uma_reserva_nao_interrompe_as_demais(self):
        def processar(driver, reserva):
            if reserva["reserva"] == "2":
                raise RuntimeError("falha simulada")
            return 0, 0, "", "", True, "OK"

        atualizar, _, _, _ = self.executar_com_reservas([{"reserva": str(i)} for i in range(1, 5)], processar)
        self.assertEqual(atualizar.call_count, 4)
        erros = [chamada for chamada in atualizar.call_args_list if not chamada.args[6]]
        self.assertEqual(len(erros), 1)
        self.assertEqual(erros[0].args[5], "2")
        self.assertIn("falha simulada", erros[0].args[7])

    def test_falha_ao_salvar_interrompe_fila_e_fecha_sessoes(self):
        reservas = [{"reserva": str(i)} for i in range(10)]
        processadas = []

        def processar(driver, reserva):
            processadas.append(reserva["reserva"])
            return 0, 0, "", "", True, "OK"

        atualizar, _, finalizar, fechar = self.executar_com_reservas(reservas, processar, gravar=OSError("Excel indisponivel"))
        atualizar.assert_called_once()
        self.assertEqual(len(processadas), 3)
        self.assertEqual(sum(chamada.args[0] is not None for chamada in finalizar.call_args_list), 3)
        fechar.assert_called_once()

    def test_falha_transitoria_recria_navegador_com_os_mesmos_cookies_sem_logar(self):
        sessao = controle._SessaoMapfre(1)
        driver_antigo = Mock(current_url="mapfre", window_handles=["1"])
        driver_novo = Mock(current_url="mapfre", window_handles=["2"])
        sessao.driver, sessao.profile_dir = driver_antigo, "perfil-antigo"
        cookies = ({"name": "autenticacao", "value": "login-atual"},)
        erro = (0, 0, "", "", False, "Sessao do navegador ficou invalida")
        sucesso = (1, 1, "orgao", "link", True, "OK")
        with patch.object(controle, "setup_driver_mapfre", return_value=(driver_novo, "perfil-novo")) as setup, \
             patch.object(controle, "finalizar_driver") as finalizar, patch.object(controle, "print", create=True), \
             patch.object(controle, "processar_reserva_arquivos", side_effect=[erro, sucesso]) as processar:
            self.assertEqual(sessao.processar(1, 1, {"reserva": "1"}, cookies), sucesso)
        setup.assert_called_once_with(cookies=cookies)
        self.assertEqual([chamada.args[0] for chamada in processar.call_args_list], [driver_antigo, driver_novo])
        self.assertEqual(finalizar.call_args.args[:2], (driver_antigo, "perfil-antigo"))

    def test_renovacao_por_tempo_aguarda_as_tres_reservas_e_faz_um_login_no_coordenador(self):
        relogio = [0]
        barreira = Barrier(3)
        lock = Lock()
        ativos = set()
        threads_login = []
        reservas = [{"reserva": str(i)} for i in range(1, 7)]

        def logar(driver):
            with lock:
                self.assertFalse(ativos)
                threads_login.append(get_ident())
            return True

        def processar(driver, reserva):
            with lock:
                ativos.add(driver)
            try:
                barreira.wait(timeout=5)
                return 0, 0, "", "", True, "OK"
            finally:
                with lock:
                    ativos.remove(driver)

        def gravar(*args, **kwargs):
            relogio[0] = 301

        with patch.object(controle.time, "monotonic", side_effect=lambda: relogio[0]):
            atualizar, login, finalizar, _ = self.executar_com_reservas(reservas, processar, gravar=gravar, ciclos=2, logar=logar)
        self.assertEqual(atualizar.call_count, 6)
        self.assertTrue(all(chamada.args[6] for chamada in atualizar.call_args_list))
        self.assertEqual(login.call_count, 2)
        self.assertEqual(threads_login, [get_ident(), get_ident()])
        self.assertEqual(sum(chamada.args[0] is not None for chamada in finalizar.call_args_list), 6)

    def test_navegador_secundario_copia_cookies_sem_fazer_login(self):
        driver = Mock()
        cookies = ({"name": "autenticacao", "value": "login-atual", "domain": "mapfre"},)
        with patch.object(controle, "criar_driver", return_value=(driver, "perfil")), patch.object(controle, "processar_login_mafre") as login:
            self.assertEqual(controle.setup_driver_mapfre(cookies=cookies), (driver, "perfil"))
        login.assert_not_called()
        driver.delete_all_cookies.assert_called_once()
        driver.add_cookie.assert_called_once_with(cookies[0])

    def test_cookies_renovados_sao_distribuidos_para_todos_os_navegadores(self):
        sessoes = [controle._SessaoMapfre(i) for i in range(1, 4)]
        drivers = [Mock() for _ in sessoes]
        cookies = [{"name": "autenticacao", "value": "novo-login"}]
        drivers[0].get_cookies.return_value = cookies
        with patch.object(controle, "setup_driver_mapfre", side_effect=[(driver, str(i)) for i, driver in enumerate(drivers)]) as setup, \
             patch.object(controle, "finalizar_driver"):
            self.assertEqual(controle._renovar_login_compartilhado(sessoes), tuple(cookies))
        self.assertEqual([chamada.kwargs["cookies"] for chamada in setup.call_args_list], [None, tuple(cookies), tuple(cookies)])

    def test_cookies_ausentes_interrompem_distribuicao_do_login(self):
        sessoes = [controle._SessaoMapfre(i) for i in range(1, 4)]
        driver = Mock()
        driver.get_cookies.return_value = []
        with patch.object(controle, "setup_driver_mapfre", return_value=(driver, "perfil")) as setup, patch.object(controle, "finalizar_driver"):
            with self.assertRaisesRegex(RuntimeError, "nao retornou cookies"):
                controle._renovar_login_compartilhado(sessoes)
        setup.assert_called_once_with(cookies=None)

    def test_login_malsucedido_fecha_driver_criado(self):
        driver = Mock()
        with patch.object(controle, "criar_driver", return_value=(driver, "perfil")), patch.object(controle, "processar_login_mafre", return_value=False), \
             patch.object(controle, "finalizar_driver") as finalizar:
            with self.assertRaisesRegex(RuntimeError, "Login Mapfre"):
                controle.setup_driver_mapfre()
        finalizar.assert_called_once_with(driver, "perfil", contexto="login Mapfre")


if __name__ == "__main__":
    unittest.main()
