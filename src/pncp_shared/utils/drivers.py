# Imports da biblioteca padrão
import contextlib
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import psutil
from unidecode import unidecode

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from pncp_shared.utils.funcoespncp import *
from pncp_shared.database.repositoriopncp import *
from pncp_shared.logs.controle_logs import logs


def caminho_base_execucao():
    """
    Quando está compilado:
        CLIENTE/obra/bot_pncpobra.exe
        retorna CLIENTE/obra

    Quando está em desenvolvimento:
        src/pncp_shared/utils/drivers.py
        retorna a raiz do projeto
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[3]


def localizar_chrome_portavel():
    base = caminho_base_execucao()

    possiveis_caminhos = [
        # Desenvolvimento
        base / "src" / "pncp_shared" / "resources" / "browser" / "chrome-win64" / "chrome.exe",
        base / "src" / "pncp_shared" / "resources" / "browser" / "chrome.exe",

        # Compilado: quando pncp_shared está dentro da mesma pasta do exe
        base / "pncp_shared" / "resources" / "browser" / "chrome-win64" / "chrome.exe",
        base / "pncp_shared" / "resources" / "browser" / "chrome.exe",

        # Compilado: quando exe está dentro de CLIENTE/obra e pncp_shared está em CLIENTE/pncp_shared
        base.parent / "pncp_shared" / "resources" / "browser" / "chrome-win64" / "chrome.exe",
        base.parent / "pncp_shared" / "resources" / "browser" / "chrome.exe",
    ]

    for caminho in possiveis_caminhos:
        if caminho.exists():
            return caminho

    return None


def localizar_chromedriver_portavel():
    base = caminho_base_execucao()

    possiveis_caminhos = [
        # Desenvolvimento
        base / "src" / "pncp_shared" / "resources" / "browser" / "chromedriver-win64" / "chromedriver.exe",
        base / "src" / "pncp_shared" / "resources" / "browser" / "chromedriver.exe",

        # Compilado: quando pncp_shared está dentro da mesma pasta do exe
        base / "pncp_shared" / "resources" / "browser" / "chromedriver-win64" / "chromedriver.exe",
        base / "pncp_shared" / "resources" / "browser" / "chromedriver.exe",

        # Compilado: quando exe está dentro de CLIENTE/obra e pncp_shared está em CLIENTE/pncp_shared
        base.parent / "pncp_shared" / "resources" / "browser" / "chromedriver-win64" / "chromedriver.exe",
        base.parent / "pncp_shared" / "resources" / "browser" / "chromedriver.exe",
    ]

    for caminho in possiveis_caminhos:
        if caminho.exists():
            return caminho

    return None


def controles_iniciais(driver):
    try:
        html = driver.find_element(By.TAG_NAME, "html")
        html = unidecode(html.get_attribute("innerHTML").lower().casefold())

        if "sua conexao nao e particular" in html or "your connection is not private" in html:
            try:
                botoes = driver.find_elements(By.TAG_NAME, "button")

                for botao in botoes:
                    bt_html = unidecode(botao.get_attribute("innerHTML").lower().casefold())

                    if "avancado" in bt_html:
                        botao.click()
                        link = driver.find_element(By.ID, "proceed-link")
                        link.click()
                        logs.info("Foi executado a acao de Conexao nao segura")
                        time.sleep(2)
                        break

            except Exception as ecn:
                logs.info("Foi detectado Conexao nao segura mas nao foi possivel executar - " + str(ecn))

    except Exception as eci:
        logs.error("Controles Iniciais - Problemas nas verificacoes - ", str(eci))


def iniciar_driver_thread(chrome_options, usar_opcao2=False, timeout=30):
    def target(q):
        try:
            with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
                chromedriver_portavel = localizar_chromedriver_portavel()

                if chromedriver_portavel:
                    logs.info(f"Usando ChromeDriver portavel: {chromedriver_portavel}")
                    service = Service(executable_path=str(chromedriver_portavel))
                    driver = webdriver.Chrome(service=service, options=chrome_options)

                elif usar_opcao2:
                    logs.info("ChromeDriver portavel nao encontrado. Usando webdriver_manager.")
                    caminho_chromedriver = ChromeDriverManager().install()
                    service = Service(executable_path=caminho_chromedriver)
                    driver = webdriver.Chrome(service=service, options=chrome_options)

                else:
                    logs.info("ChromeDriver portavel nao encontrado. Usando Selenium Manager.")
                    driver = webdriver.Chrome(options=chrome_options)

                driver.implicitly_wait(10)
                q.put(driver)

        except Exception as e:
            q.put(e)

    q = queue.Queue()
    t = threading.Thread(target=target, args=(q,), daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise TimeoutError(f"Timeout ao iniciar o ChromeDriver apos {timeout}s")

    if q.empty():
        raise RuntimeError("A thread de criacao do driver terminou sem retornar resultado.")

    result = q.get()

    if isinstance(result, Exception):
        raise result

    if result is None:
        raise RuntimeError("O driver retornou None.")

    return result


def _matar_arvore_processo(pid):
    if not pid:
        return

    try:
        processo = psutil.Process(pid)

        for filho in processo.children(recursive=True):
            filho.kill()

        processo.kill()

    except Exception:
        pass


def _matar_chromes_do_perfil(profile_dir):
    if not profile_dir:
        return

    profile_dir_normalizado = os.path.normcase(os.path.abspath(str(profile_dir)))

    for processo in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            nome = (processo.info.get("name") or "").lower()
            if "chrome" not in nome and "chromedriver" not in nome:
                continue

            cmdline = " ".join(processo.info.get("cmdline") or [])
            cmdline_normalizado = os.path.normcase(cmdline)

            if profile_dir_normalizado in cmdline_normalizado:
                _matar_arvore_processo(processo.info["pid"])

        except Exception:
            pass


def encerrar_driver_com_timeout(driver, timeout: int = 15):
    """
    Encerra o WebDriver em thread separada com timeout.
    Minimiza arquivos temporarios e evita travamentos do programa.
    """
    service_pid = None
    profile_dir = getattr(driver, "profile_dir", None)

    try:
        if driver.service and driver.service.process:
            service_pid = driver.service.process.pid
    except Exception:
        service_pid = None

    def fechar_driver():
        try:
            driver.quit()
        except Exception:
            pass

    thread = threading.Thread(target=fechar_driver, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        _matar_arvore_processo(service_pid)

    _matar_chromes_do_perfil(profile_dir)

    time.sleep(0.5)


def finalizar_driver(driver=None, profile_dir=None, timeout: int = 15, contexto: str = "driver"):
    """
    Fecha o WebDriver e remove o perfil temporario usado pela sessao.
    Tambem derruba Chromes orfaos que tenham sido abertos com esse perfil.
    """
    profile_dir = profile_dir or getattr(driver, "profile_dir", None)

    if driver:
        try:
            encerrar_driver_com_timeout(driver, timeout=timeout)
        except Exception as e:
            logs.error(f"Erro ao encerrar {contexto}: {e}")

    _matar_chromes_do_perfil(profile_dir)

    if profile_dir:
        shutil.rmtree(profile_dir, ignore_errors=True)


def criar_driver(mostrar_browser=False):
    profile_dir = tempfile.mkdtemp(prefix="pncp_chrome_")
    download_dir = os.path.join(profile_dir, "downloads")
    os.makedirs(download_dir, exist_ok=True)

    chrome_options = Options()

    chrome_portavel = localizar_chrome_portavel()

    if chrome_portavel:
        logs.info(f"Usando Chrome portavel: {chrome_portavel}")
        chrome_options.binary_location = str(chrome_portavel)
    else:
        logs.info("Chrome portavel nao encontrado. Usando Chrome instalado no sistema.")

    chrome_options.add_argument(f"--user-data-dir={profile_dir}")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--window-size=1920,1080")

    if not mostrar_browser:
        chrome_options.add_argument("--headless=new")

    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    })

    try:
        driver = iniciar_driver_thread(chrome_options, usar_opcao2=False, timeout=30)

        if driver is None:
            raise RuntimeError("A primeira tentativa retornou driver=None.")

        driver.set_page_load_timeout(60)
        driver.download_dir = download_dir
        driver.profile_dir = profile_dir

        return driver, profile_dir

    except Exception as e1:
        try:
            logs.error(f"Primeira tentativa de criar driver falhou: {e1}")

            driver = iniciar_driver_thread(chrome_options, usar_opcao2=True, timeout=30)

            if driver is None:
                raise RuntimeError("A segunda tentativa retornou driver=None.")

            driver.set_page_load_timeout(60)
            driver.download_dir = download_dir
            driver.profile_dir = profile_dir

            return driver, profile_dir

        except Exception as e2:
            shutil.rmtree(profile_dir, ignore_errors=True)

            raise RuntimeError(
                f"Falha ao criar driver nas duas tentativas. "
                f"Primeira tentativa: {e1} | Segunda tentativa: {e2}"
            ) from e2


def acessar_url(driver, url_base, plataforma, processar_dia, hora_atual):
    try:
        if processar_dia and 5 <= hora_atual < 9:
            url = url_base.replace(
                next((part for part in url_base.split('&') if part.startswith('tam_pagina=')), '&tam_pagina=20'),
                'tam_pagina=50'
            )
        else:
            url = url_base

        if driver is None:
            raise ValueError("O driver veio None ao tentar acessar a URL.")

        if not url or not str(url).strip():
            raise ValueError("A URL esta vazia ou invalida.")

        driver.get(url)

    except Exception as e:
        logs.error(f"ERRO ao acessar URL: {str(e)}")
        logs.error(traceback.format_exc())
        time.sleep(0.2)
        raise
