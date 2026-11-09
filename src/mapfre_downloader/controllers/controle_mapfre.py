import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Lock

from pncp_shared.utils.funcoespncp import limpar_console
from pncp_shared.logs.controle_logs import controle_logs, logs
from pncp_shared.config.controle_config import carregar_configuracoes, config, configuracoes
from mapfre_downloader.services.excel_service import ler_links_excel, atualizar_planilha, fechar_planilha
from mapfre_downloader.services.mapfre_service import processar_login_mafre
from pncp_shared.utils.drivers import criar_driver, finalizar_driver
from mapfre_downloader.services.download_service import processar_reserva_arquivos


_lock_driver = Lock()
_ERROS_TRANSITORIOS = ("janela do arquivo foi fechada antes do download", "carregamento da aba do arquivo foi interrompido",
                       "sessao do navegador foi encerrada", "sessao do navegador ficou invalida", "conexao com o navegador foi recusada")


class _SessaoMapfre:
    def __init__(self, numero):
        self.numero = numero
        self.driver = None
        self.profile_dir = None

    def fechar(self):
        driver, profile_dir = self.driver, self.profile_dir
        self.driver, self.profile_dir = None, None
        finalizar_driver(driver, profile_dir, contexto=f"driver Mapfre {self.numero}")

    def abrir(self, cookies):
        self.fechar()
        self.driver, self.profile_dir = setup_driver_mapfre(cookies=cookies)

    def processar(self, indice, total, reserva, cookies_login):
        id_reserva = reserva.get("reserva", "")
        logs.info("Sessao %s - Iniciando reserva %s/%s: %s", self.numero, indice, total, id_reserva)
        print(f"\nSessao {self.numero} - Iniciando reserva {indice}/{total}: {id_reserva}")
        try:
            driver_disponivel = False
            if self.driver:
                try:
                    _ = self.driver.current_url
                    _ = self.driver.window_handles
                    driver_disponivel = True
                except Exception:
                    logs.warning("Sessao %s - Driver indisponivel. Recriando sessao.", self.numero)

            if not driver_disponivel:
                self.abrir(cookies_login)

            resultado = processar_reserva_arquivos(self.driver, reserva)
            if not resultado[4] and any(erro in str(resultado[5]).lower() for erro in _ERROS_TRANSITORIOS):
                logs.warning("Sessao %s - Falha transitoria na reserva %s. Recriando navegador com o login atual.", self.numero, id_reserva)
                self.abrir(cookies_login)
                resultado = processar_reserva_arquivos(self.driver, reserva)
            return resultado
        except Exception as ex:
            logs.exception("Sessao %s - ERRO ao processar reserva %s/%s: %s", self.numero, indice, total, id_reserva)
            return 0, 0, "", "", False, f"ERRO - Ao processar reserva: {ex}"


def _renovar_login_compartilhado(sessoes):
    # O coordenador chama esta funcao somente quando nao ha reservas em andamento.
    for sessao in sessoes:
        sessao.fechar()
    sessoes[0].abrir(None)
    cookies = tuple(sessoes[0].driver.get_cookies())
    if not cookies:
        raise RuntimeError("Login Mapfre nao retornou cookies para compartilhar a autenticacao")
    for sessao in sessoes[1:]:
        sessao.abrir(cookies)
    logs.info("Login Mapfre realizado uma vez e compartilhado com %s navegadores.", len(sessoes))
    return cookies


def _chave_reserva(reserva):
    return str(reserva.get("reserva", "")).strip().replace(".0", "")


def _retirar_proxima_reserva(fila, reservas_ativas):
    # Reservas repetidas podem usar a mesma pasta e ZIP; nunca devem rodar juntas.
    for _ in range(len(fila)):
        indice, reserva = fila.popleft()
        if _chave_reserva(reserva) not in reservas_ativas:
            return indice, reserva
        fila.append((indice, reserva))
    return None


def executar_bot_mapfre():
    sessoes = []
    try:
        limpar_console()
        carregar_configuracoes(nome_pacote="mapfre_downloader")
        controle_logs()
        caminho_excel = config("caminho_excel")
        quantidade_sessoes = int(configuracoes.get("links_simultaneos", 3))
        if quantidade_sessoes not in (1, 2, 3):
            raise ValueError("links_simultaneos deve ser 1, 2 ou 3")

        reservas = ler_links_excel(caminho_excel)
        if not reservas:
            logs.info("Nenhuma reserva encontrada no Excel.")
            return

        sessoes = [_SessaoMapfre(numero) for numero in range(1, min(quantidade_sessoes, len(reservas)) + 1)]
        cookies_login = _renovar_login_compartilhado(sessoes)
        instante_ultimo_login = time.monotonic()
        sessoes_livres = list(sessoes)
        fila = deque(enumerate(reservas, start=1))
        futuros = {}
        reservas_ativas = set()
        instante_ultima_manutencao = time.monotonic()
        inicio = time.monotonic()
        concluidas = 0
        logs.info("Bot Mapfre iniciado com %s sessoes para %s reservas.", len(sessoes), len(reservas))
        print(f"Bot Mapfre iniciado com {len(sessoes)} sessoes para {len(reservas)} reservas.")

        # O coordenador cuida do login e do Excel; os navegadores compartilham a autenticacao.
        with ThreadPoolExecutor(max_workers=len(sessoes), thread_name_prefix="mapfre") as executor:
            while fila or futuros:
                intervalo_config = float(configuracoes.get("tempo_recarregar_config", 900))
                if time.monotonic() - instante_ultima_manutencao >= intervalo_config:
                    carregar_configuracoes(nome_pacote="mapfre_downloader")
                    controle_logs()
                    instante_ultima_manutencao = time.monotonic()
                    logs.info("Configuracoes recarregadas durante o processamento do Excel.")

                tempo_login = float(configuracoes.get("tempo_de_login", 300))
                renovar_login = bool(fila) and time.monotonic() - instante_ultimo_login >= tempo_login
                if renovar_login and not futuros:
                    cookies_login = _renovar_login_compartilhado(sessoes)
                    instante_ultimo_login = time.monotonic()
                    renovar_login = False

                # Aguarda as reservas atuais antes de trocar os cookies de todos os navegadores.
                for sessao in list(sessoes_livres) if not renovar_login else []:
                    proxima = _retirar_proxima_reserva(fila, reservas_ativas)
                    if proxima is None:
                        break
                    indice, reserva = proxima
                    futuro = executor.submit(sessao.processar, indice, len(reservas), reserva, cookies_login)
                    futuros[futuro] = sessao, indice, reserva
                    reservas_ativas.add(_chave_reserva(reserva))
                    sessoes_livres.remove(sessao)

                concluidos, _ = wait(futuros, timeout=1, return_when=FIRST_COMPLETED)
                for futuro in concluidos:
                    sessao, indice, reserva = futuros.pop(futuro)
                    quantidade_arquivos, quantidade_baixado, orgao, link, processou, msg = futuro.result()
                    atualizar_planilha(quantidade_arquivos, quantidade_baixado, orgao, link, caminho_excel, reserva.get("reserva", ""),
                                       processou, msg, linha_excel=reserva.get("linha_excel"))
                    reservas_ativas.remove(_chave_reserva(reserva))
                    sessoes_livres.append(sessao)
                    concluidas += 1
                    horas = max((time.monotonic() - inicio) / 3600, 1 / 3600)
                    ritmo = concluidas / horas
                    restantes_horas = (len(reservas) - concluidas) / ritmo
                    progresso = f"Concluidas {concluidas}/{len(reservas)} | {ritmo:.1f} reservas/h | Restante estimado: {restantes_horas:.1f} h"
                    logs.info("Sessao %s - Reserva %s/%s finalizada. %s", sessao.numero, indice, len(reservas), progresso)
                    print(progresso)

        logs.info("Bot Mapfre finalizado.")
    except Exception as ex:
        logs.exception("ERRO ao executar o bot Mapfre")
        print(f"ERRO FATAL - Ao executar o bot Mapfre: {ex}")
    finally:
        try:
            fechar_planilha()
        finally:
            for sessao in sessoes:
                sessao.fechar()


def setup_driver_mapfre(cookies=None):
    # A criacao do driver redireciona stderr e precisa ser serializada.
    with _lock_driver:
        driver, profile_dir = criar_driver(mostrar_browser=False)
        try:
            driver.get(configuracoes.get("mafre", {}).get("url_login"))
            if cookies is not None:
                driver.delete_all_cookies()
                for cookie in cookies:
                    driver.add_cookie(dict(cookie))
            elif not processar_login_mafre(driver):
                raise RuntimeError("ERRO - Login Mapfre nao foi realizado")
            return driver, profile_dir
        except Exception:
            finalizar_driver(driver, profile_dir, contexto="login Mapfre")
            raise
