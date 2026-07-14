import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from pncp_shared.utils.drivers import controles_iniciais
from pncp_shared.config.controle_config import configuracoes
from pncp_shared.logs.controle_logs import logs



def wait_for_updatepanel(driver, timeout=10, stable_time=0.3):
    """Aguarda o DOM ficar estável (sem mudanças) por stable_time segundos consecutivos."""
    start_time = time.time()
    last_html = driver.page_source
    last_change = time.time()

    while time.time() - start_time < timeout:
        time.sleep(0.1)
        current_html = driver.page_source
        if current_html != last_html:
            last_change = time.time()
            last_html = current_html
        elif time.time() - last_change >= stable_time:
            return 

    raise TimeoutError("Timeout esperando UpdatePanel ou DOM estabilizar.")


def wait_until_input_ready(driver, by, value, timeout=15):
    def input_is_empty_and_ready(drv):
        try:
            el = drv.find_element(by, value)
            return el.is_displayed() and el.is_enabled() and el.get_attribute("value") == ""
        except:
            return False

    WebDriverWait(driver, timeout).until(input_is_empty_and_ready)

def processar_login_mafre(driver_mapfre):
    tentativas = 0
    max_tentativas = 2
    while tentativas < max_tentativas:
        try:
            user = configuracoes.get("mafre", {}).get("user")
            password = configuracoes.get("mafre", {}).get("password")
            
            controles_iniciais(driver_mapfre)
            
            WebDriverWait(driver_mapfre, 20).until(EC.presence_of_all_elements_located((By.XPATH, "/html/body/form/div[3]/div/div/div[2]")))

            usuario = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.XPATH, ".//table/tbody/tr[1]/td[2]/input")))
            usuario.send_keys(user)

            senha = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.XPATH, ".//table/tbody/tr[2]/td[2]/input")))
            senha.send_keys(password)

            botao_login = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.ID, "btnLogin")))
            botao_login.click()
            
            try:
                WebDriverWait(driver_mapfre, 40).until(EC.presence_of_element_located((By.ID, "btnConfirmaTermos")))
                print("✅ Login bem-sucedido")
                return True
               
            except:
                try:
                    # Tenta verificar se a senha está expirada
                    WebDriverWait(driver_mapfre, 10).until(EC.presence_of_element_located((By.ID, "lblFormTitle")))
                    if trocar_senha(driver_mapfre, password):
                        print("🔁 Senha expirada, mas login continuará após troca.")
                        return True

                    print("❌ Falha ao trocar senha expirada")
                    return False

                except Exception:
                    print("❌ Falha no login")
                    tentativas += 1
                    if tentativas >= max_tentativas:
                        return False
        except Exception as ex:
            tentativas += 1
            if tentativas >= max_tentativas:
                logs.error("processar_login_mafre - tentativa %d - %s", tentativas + 1, str(ex))
                return False
    return False

def trocar_senha(driver_mapfre, password):
    tentativas = 0
    max_tentativas = 2
    while tentativas < max_tentativas:
        try:
            WebDriverWait(driver_mapfre, 20).until(EC.presence_of_all_elements_located((By.ID, "UpdatePanel")))
            
            txtSenha = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.ID, "txtSenha")))
            time.sleep(0.5)
            txtSenha.send_keys(password)
            time.sleep(0.5)
            txtNsenha = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.ID, "txtNsenha")))
            time.sleep(0.5)
            txtNsenha.send_keys(password)
            time.sleep(0.5)
            txtCsenha = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.ID, "txtCsenha")))
            time.sleep(0.5)
            txtCsenha.send_keys(password)
            time.sleep(0.5)
            botao_gravar = WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.ID, "btnUpdate")))
            time.sleep(0.5)
            botao_gravar.click()
            return True
            
        except Exception as ex: 
            tentativas += 1
            if tentativas >= max_tentativas:
                logs.error("trocar_senha - ", str(ex))
                return False
    return False
  
