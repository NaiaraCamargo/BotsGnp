# Imports da biblioteca padrão
import contextlib
import time
import queue
import shutil
import threading
import tempfile
from unidecode import unidecode
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import psutil
import traceback

# Imports de módulos locais
from funcoespncp import *
from repositoriopncp import *
from controle_logs import logs


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
                if usar_opcao2:
                    caminho_chromedriver = ChromeDriverManager().install()
                    service = Service(executable_path=caminho_chromedriver)
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
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
        raise TimeoutError(f"Timeout ao iniciar o ChromeDriver após {timeout}s")

    if q.empty():
        raise RuntimeError("A thread de criação do driver terminou sem retornar resultado.")

    result = q.get()

    if isinstance(result, Exception):
        raise result

    if result is None:
        raise RuntimeError("O driver retornou None.")

    return result

def encerrar_driver_com_timeout(driver, timeout: int = 15):
    """
    Encerra o WebDriver em thread separada com timeout.
    Minimiza arquivos temporários e evita travamentos do programa.
    """
    def fechar_driver():
        try:
            driver.quit()
        except Exception:
            pass

    thread = threading.Thread(target=fechar_driver)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        try:
            if driver.service and driver.service.process:
                pid = driver.service.process.pid
                process = psutil.Process(pid)
                for child in process.children(recursive=True):
                    child.kill()  # Mata subprocessos do ChromeDriver
                process.kill()
        except Exception:
            pass

    # Pequena pausa para garantir que arquivos temporários sejam liberados
    time.sleep(0.5)
        
def criar_driver(mostrar_browser=False):
    profile_dir = tempfile.mkdtemp()

    chrome_options = Options()
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=0")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    if not mostrar_browser:
        chrome_options.add_argument("--headless")      
    try:
        driver = iniciar_driver_thread(chrome_options, usar_opcao2=False, timeout=30)

        if driver is None:
            raise RuntimeError("A primeira tentativa retornou driver=None.")

        return driver, profile_dir

    except Exception as e1:
        try:
            driver = iniciar_driver_thread(chrome_options, usar_opcao2=True, timeout=30)

            if driver is None:
                raise RuntimeError("A segunda tentativa retornou driver=None.")

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
            raise ValueError("A URL está vazia ou inválida.")

        driver.get(url)

    except Exception as e:
        import traceback
        logs.error(f"ERRO ao acessar URL: {str(e)}")
        logs.error(traceback.format_exc())
        time.sleep(0.2)
        raise