# Imports da biblioteca padrão
import time
import queue
import shutil
import threading
import tempfile
import traceback
from unidecode import unidecode
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

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

def encerrar_driver_com_timeout(driver, timeout=5):
    def target():
        try:
            driver.quit()
        except Exception as e:
            logs.warning(f"[AVISO] Erro ao tentar fechar o driver: {e}")
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logs.warning("[AVISO] driver.quit() travou e foi abandonado")
        
def criar_driver(mostrar_browser=False):
      # Cria um diretório temporário para perfil isolado
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
        logs.error(f"[CRITICAL] Erro ao iniciar Chrome via PATH: {e1}")
        # Segunda tentativa: baixar e usar ChromeDriver com timeout
        try:
            driver = iniciar_driver_thread(chrome_options, usar_opcao2=True)
        except Exception as e2:
            logs.error(f"[FATAL] Falha ao baixar/iniciar ChromeDriver: {e2}")
            logs.debug(traceback.format_exc())
            shutil.rmtree(profile_dir, ignore_errors=True)
            raise RuntimeError(f"Falha total ao iniciar o ChromeDriver: {e2}") from e2

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
        logs.warning(f"Erro ao acessar a URL '{url_base}': {e}. Tentando novamente...")
        time.sleep(0.2)
        raise