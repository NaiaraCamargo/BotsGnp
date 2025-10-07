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


# Imports de módulos locais
from funcoespncp import *
from gerar_planilha import *
from repositoriopncp import *

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
        
def iniciar_driver_thread(chrome_options, usar_opcao2=False, timeout=10):
    def target(q):
        try:
            with open(os.devnull, 'w') as devnull, contextlib.redirect_stderr(devnull):
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
        raise TimeoutError("Timeout ao iniciar o ChromeDriver")

    result = q.get()
    if isinstance(result, Exception):
        raise result
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

    if not mostrar_browser:
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument('--log-level=3')  # Log mínimo
    driver = None

    # Tenta iniciar Chrome via PATH com timeout
    try:
        driver = iniciar_driver_thread(chrome_options)
    except Exception as e1:
        # Segunda tentativa: baixar e usar ChromeDriver com timeout
        try:
            driver = iniciar_driver_thread(chrome_options, usar_opcao2=True)
        except Exception as e2:
            shutil.rmtree(profile_dir, ignore_errors=True)

    return driver, profile_dir


def acessar_url(driver, url_base, plataforma, processar_dia, hora_atual):
    try:
        if processar_dia and 5 <= hora_atual < 9:
            if plataforma == "obra":
                 # Substitui o trecho &tam_pagina=XX por &tam_pagina=50
                url = url_base.replace(
                    next((part for part in url_base.split('&') if part.startswith('tam_pagina=')), '&tam_pagina=20'),
                    'tam_pagina=50'
                )
            else:
                url = url_base + "&tam_pagina=50"
        else:
            url = url_base
        driver.get(url)
    except Exception as e:
        time.sleep(0.2)
        raise