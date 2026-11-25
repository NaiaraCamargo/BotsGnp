import unittest
from contextlib import ExitStack
from threading import Barrier, Lock, get_ident
from unittest.mock import Mock, patch

from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import ProtocolError

from mapfre_downloader.controllers import controle_mapfre as controle
from mapfre_downloader.services import download_service as download


class ControleMapfreTest(unittest.TestCase):
    def test_reset_de_conexao_na_paginacao_nao_retorna_lista_vazia(self):
        erro = ProtocolError("Connection aborted.", ConnectionResetError(10054, "Conexao encerrada"))
        driver = Mock()
        driver.find_elements.side_effect = erro
        with patch.object(download, "logs"):
            with self.assertRaises(ProtocolError):
                download.extrair_paginas_grd_docs(driver)
        self.assertTrue(download.erro_transitorio_de_janela_ou_sessao(erro))
        self.assertEqual(download.mensagem_resumida_erro(erro), "Sessao do navegador foi encerrada")

    def test_grid_sem_paginacao_continua_retornando_lista_vazia(self):
        driver = Mock()
        driver.find_elements.return_value = []
        self.assertEqual(download.extrair_paginas_grd_docs(driver), [])

    def test_reset_na_grid_recria_navegador_e_repete_reserva(self):
        erro = ProtocolError("Connection aborted.", ConnectionResetError(10054, "Conexao encerrada"))
        sessao = controle._SessaoMapfre(1)
        driver_antigo = Mock(current_url="mapfre", window_handles=["1"])
        driver_novo = Mock(current_url="mapfre", window_handles=["2"])
        sessao.driver, sessao.profile_dir = driver_antigo, "perfil-antigo"
        cookies = ({"name": "autenticacao", "value": "login-atual"},)
        config = {"mafre": {"url_arquivo_digital": "https://teste/cadArquivoDigital.aspx?id=0"}}
        with patch.dict(download.configuracoes, config, clear=True), patch.object(download, "WebDriverWait"), patch.object(download, "logs"), \
             patch.object(download, "extrair_arquivos_grd_docs", return_value=[]), patch.object(download, "extrair_paginas_grd_docs", side_effect=erro):
            falha = download.processar_reserva_arquivos(driver_antigo, {"reserva": "1"})
        self.assertFalse(falha[4])
        self.assertIn("Sessao do navegador foi encerrada", falha[5])
        sucesso = (1, 1, "orgao", "link", True, "OK")
        with patch.object(controle, "setup_driver_mapfre", return_value=(driver_novo, "perfil-novo")) as setup, \
             patch.object(controle, "finalizar_driver"), patch.object(controle, "print", create=True), \
             patch.object(controle, "processar_reserva_arquivos", side_effect=[falha, sucesso]) as processar:
            self.assertEqual(sessao.processar(1, 1, {"reserva": "1"}, cookies), sucesso)
        setup.assert_called_once_with(cookies=cookies)
        self.assertEqual([chamada.args[0] for chamada in processar.call_args_list], [driver_antigo, driver_novo])

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

    def test_falhas_consecutivas_no_login_retentam_ate_recuperar(self):
        sessoes = [Mock() for _ in range(3)]
        cookies = ({"name": "autenticacao", "value": "login-recuperado"},)
        falha = WebDriverException("unknown error: net::ERR_CONNECTION_TIMED_OUT\nStacktrace: detalhes do Chrome")
        with patch.object(controle, "_renovar_login_compartilhado", side_effect=[falha, falha, falha, cookies]) as renovar, \
             patch.object(controle, "salvar_alteracoes_planilha") as salvar, patch.object(controle.time, "sleep") as esperar, \
             patch.object(controle, "print", create=True), patch.object(controle, "logs") as logs:
            self.assertEqual(controle._aguardar_login_compartilhado(sessoes), cookies)
        self.assertEqual(renovar.call_count, 4)
        self.assertEqual([chamada.args[0] for chamada in esperar.call_args_list], [30, 30, 30])
        salvar.assert_called_once_with(forcar=True)
        for sessao in sessoes:
            self.assertEqual(sessao.fechar.call_count, 3)
        self.assertEqual(logs.warning.call_count, 3)
        self.assertIn("ERR_CONNECTION_TIMED_OUT", logs.warning.call_args.args[0])
        self.assertNotIn("Stacktrace", logs.warning.call_args.args[0])
        self.assertIn("Retomando", logs.info.call_args.args[0])

    def test_timeout_na_renovacao_preserva_a_fila_e_nao_repete_reservas_concluidas(self):
        relogio = [0]
        processadas = []
        tentativas = 0
        renovar_original = controle._renovar_login_compartilhado

        def renovar(sessoes):
            nonlocal tentativas
            tentativas += 1
            if tentativas == 2:
                raise WebDriverException("unknown error: net::ERR_CONNECTION_TIMED_OUT")
            return renovar_original(sessoes)

        def processar(driver, reserva):
            processadas.append(reserva["reserva"])
            return 0, 0, "", "", True, "OK"

        def gravar(*args, **kwargs):
            relogio[0] = 301

        with patch.object(controle.time, "monotonic", side_effect=lambda: relogio[0]), patch.object(controle.time, "sleep") as esperar, \
             patch.object(controle, "_renovar_login_compartilhado", side_effect=renovar), patch.object(controle, "salvar_alteracoes_planilha") as salvar:
            atualizar, login, _, fechar = self.executar_com_reservas([{"reserva": str(i)} for i in range(1, 4)], processar, quantidade=1, gravar=gravar, ciclos=2)
        self.assertEqual(processadas, ["1", "2", "3"])
        self.assertEqual(atualizar.call_count, 3)
        self.assertTrue(all(chamada.args[6] for chamada in atualizar.call_args_list))
        self.assertEqual(login.call_count, 2)
        self.assertEqual(tentativas, 3)
        esperar.assert_called_once_with(30)
        salvar.assert_called_once_with(forcar=True)
        fechar.assert_called_once()

    def test_timeout_no_login_inicial_recupera_antes_de_processar_reservas(self):
        tentativas = 0

        def logar(driver):
            nonlocal tentativas
            tentativas += 1
            if tentativas == 1:
                raise WebDriverException("unknown error: net::ERR_CONNECTION_TIMED_OUT")
            return True

        with patch.object(controle.time, "sleep") as esperar, patch.object(controle, "salvar_alteracoes_planilha") as salvar:
            atualizar, login, finalizar, _ = self.executar_com_reservas([{"reserva": "1"}], lambda *args: (0, 0, "", "", True, "OK"), quantidade=1, ciclos=2, logar=logar)
        self.assertEqual(login.call_count, 2)
        atualizar.assert_called_once()
        self.assertTrue(atualizar.call_args.args[6])
        self.assertEqual(sum(chamada.args[0] is not None for chamada in finalizar.call_args_list), 2)
        esperar.assert_called_once_with(30)
        salvar.assert_called_once_with(forcar=True)

    def test_interrupcao_manual_nao_e_tratada_como_falha_de_login(self):
        with patch.object(controle, "_renovar_login_compartilhado", side_effect=KeyboardInterrupt), patch.object(controle.time, "sleep") as esperar:
            with self.assertRaises(KeyboardInterrupt):
                controle._aguardar_login_compartilhado([Mock()])
        esperar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
