# Imports da biblioteca padrão
import os
import re
from datetime import datetime
from unidecode import unidecode
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException, ElementClickInterceptedException
# Imports de módulos locais
from funcoespncp import *
from funcoesmapfre import *
from gerar_planilha import *
from repositoriopncp import *
from drivers import *
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup
from urllib.parse import urljoin


# --- Aqui já define a função utilitária ---
def wait_for_dom_stable(driver, timeout=10, stable_time=0.3):
    """
    Aguarda o DOM ficar estável (sem mudanças) por stable_time segundos consecutivos.
    """
    start_time = time.time()
    last_html = driver.page_source
    last_change = time.time()

    while time.time() - start_time < timeout:
        time.sleep(0.2)  # um pouco maior para reduzir CPU
        try:
            current_html = driver.page_source
        except Exception:
            # Se a página está em transição, ignora e continua
            continue

        if current_html != last_html:
            last_change = time.time()
            last_html = current_html
        elif time.time() - last_change >= stable_time:
            return True  # DOM está estável

    raise TimeoutError("Timeout esperando o DOM estabilizar.")

# --- Se ainda não tiver, defina essa também ---
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
            
            WebDriverWait(driver_mapfre, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, "/html/body/form/div[3]/div/div/div[2]"))
            )

            usuario = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.XPATH, ".//table/tbody/tr[1]/td[2]/input"))
            )
            usuario.send_keys(user)

            senha = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.XPATH, ".//table/tbody/tr[2]/td[2]/input"))
            )
            senha.send_keys(password)

            botao_login = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.ID, "btnLogin"))
            )
            botao_login.click()
            
            try:
                WebDriverWait(driver_mapfre, 40).until(
                    EC.presence_of_element_located((By.ID, "btnConfirmaTermos"))
                )
                print("✅ Login bem-sucedido")
                return
               
            except:
                try:
                    # Tenta verificar se a senha está expirada
                    WebDriverWait(driver_mapfre, 10).until(
                        EC.presence_of_element_located((By.ID, "lblFormTitle"))
                    )
                    trocar_senha(driver_mapfre, password)
                    print("🔁 Senha expirada, mas login continuará após troca.")
                    return

                except Exception:
                    print("❌ Falha no login")
                    tentativas += 1
                    if tentativas >= max_tentativas:
                     return
        except Exception as ex:
            tentativas += 1
            if tentativas >= max_tentativas:
                logs.error("processar_login_mafre - tentativa %d - %s", tentativas + 1, str(ex))
                return 
    return

def trocar_senha(driver_mapfre, password):
    tentativas = 0
    max_tentativas = 2
    while tentativas < max_tentativas:
        try:
            WebDriverWait(driver_mapfre, 20).until(
                EC.presence_of_all_elements_located((By.ID, "UpdatePanel"))
            )
            
            txtSenha = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.ID, "txtSenha"))
            )
            time.sleep(0.5)
            txtSenha.send_keys(password)
            time.sleep(0.5)
            txtNsenha = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.ID, "txtNsenha"))
            )
            time.sleep(0.5)
            txtNsenha.send_keys(password)
            time.sleep(0.5)
            txtCsenha = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.ID, "txtCsenha"))
            )
            time.sleep(0.5)
            txtCsenha.send_keys(password)
            time.sleep(0.5)
            botao_gravar = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.ID, "btnUpdate"))
            )
            time.sleep(0.5)
            botao_gravar.click()
            
        except Exception as ex: 
            tentativas += 1
            if tentativas >= max_tentativas:
                logs.error("trocar_senha - ", str(ex))
                return "Erro ao processar trocar senha; ", ""
   

def processar_pos_login(driver_mapfre, edital, thread_download):
    tentativas = 0
    max_tentativas = 3
    while tentativas < max_tentativas:
        try:
            msg = ""
            links = []
            imgs = [] 
            url_pos_login = configuracoes.get("mafre", {}).get("url_pos_login")
            driver_mapfre.get(url_pos_login)
         
            form_screen = WebDriverWait(driver_mapfre, 20).until(
                EC.presence_of_element_located((By.ID, "UpdatePanel"))
            )
            filtro_pesquisa = form_screen.find_element(By.ID, "cmbFilter")
            select_filtro = Select(filtro_pesquisa)
            select_filtro.select_by_value("cpf_cnpj")
            wait_for_dom_stable(driver_mapfre)

            ##wait_until_input_ready(driver_mapfre, By.ID, "txtFilter")
            form_screen = WebDriverWait(driver_mapfre, 20).until(
                EC.presence_of_element_located((By.ID, "UpdatePanel"))
            )
            texto_pesquisa = form_screen.find_element(By.ID, "txtFilter")
            cnpj_pesquisa = cnpj_formatado(edital.get("Cnpj", ""))
            texto_pesquisa.clear()
            texto_pesquisa.send_keys(cnpj_pesquisa)
            texto_pesquisa.send_keys(Keys.TAB)  

            # Aguarda o campo ser refletido corretamente com o valor esperado
            WebDriverWait(driver_mapfre, 10).until(
                lambda d: d.find_element(By.ID, "txtFilter").get_attribute("value") != ""
            )
            valor_input = driver_mapfre.find_element(By.ID, "txtFilter").get_attribute("value")      
            print(f"Valor do cnpj pesquisa:{cnpj_pesquisa}")
            logs.warning(f"Valor do cnpj pesquisa:{cnpj_pesquisa}")
            print(f"Valor do input:{valor_input}")
            logs.warning(f"Valor do input:{valor_input}")
           
            try:
                botao_filter  = WebDriverWait(driver_mapfre, 20).until(
                    EC.element_to_be_clickable((By.ID, "btnFilter"))
                )
                botao_filter.click()
                WebDriverWait(driver_mapfre, 15).until(EC.staleness_of(botao_filter))
            except (StaleElementReferenceException, ElementClickInterceptedException) as ex:
                botao_filter  = WebDriverWait(driver_mapfre, 15).until(
                    EC.element_to_be_clickable((By.ID, "btnFilter"))
                )
                driver_mapfre.execute_script("arguments[0].click();", botao_filter)     
                WebDriverWait(driver_mapfre, 15).until(EC.staleness_of(botao_filter))        
            try: 
                wait_for_dom_stable(driver_mapfre)
                grd_cliente = WebDriverWait(driver_mapfre, 30).until(
                    EC.presence_of_element_located((By.ID, 'grdCliente'))
                )
                
                cnpj_elem = grd_cliente.find_element(By.XPATH, '//*[@id="grdCliente"]/tbody/tr[2]/td[5]')
                cnpj_encontrado= cnpj_elem.text.strip()
                logs.warning(f"CNPJ encontrado:{cnpj_encontrado}")
                print(f"CNPJ encontrado:{cnpj_encontrado}")
                 
                botao_reserva = WebDriverWait(driver_mapfre, 15).until(
                    EC.element_to_be_clickable((By.ID, "btnLicitacao"))
                )
                botao_reserva.click()
            
                status = clicar_new_rerserva(driver_mapfre)
                
                if status:
                    msg, links, imgs = preencher_form_licitacao(driver_mapfre, edital, thread_download)
                else:
                    msg += "Erro ao tentar clicar em incluir reserva;"
                return msg, links, imgs
                
            except Exception as ex:
                print(f"❌ NÃO HÁ REGISTRO PARA ESSE CNPJ: {edital['Cnpj']}")
                logs.error("processar_pos_login - ", str(ex))
                tentativas += 1
                if tentativas >= max_tentativas:
                    logs.error("processar_pos_login - ", str(ex))
                    return "NÃO HÁ REGISTRO PARA ESSE CNPJ;", [], [] 
                
        except Exception as ex:
            tentativas += 1
            logs.error("processar_pos_login - ", str(ex))
            if tentativas >= max_tentativas:
                logs.error("processar_pos_login - ", str(ex))
                return "Erro ao processar pagina pos login;", [], []
    

def clicar_new_rerserva(driver_mapfre):
    tentativas = 0
    max_tentativas = 3
    while tentativas < max_tentativas:
        try:
            WebDriverWait(driver_mapfre, 15).until(
                EC.element_to_be_clickable((By.ID, "formScreen"))
            )
            
            botao_new  = WebDriverWait(driver_mapfre, 15).until(
                EC.element_to_be_clickable((By.ID, "btnNew"))
            )
            driver_mapfre.execute_script("arguments[0].focus(); arguments[0].click();", botao_new)    
            WebDriverWait(driver_mapfre, 20).until(EC.staleness_of(botao_new))
            
            status_elem = WebDriverWait(driver_mapfre, 20).until(
                EC.visibility_of_element_located((By.ID, "lblStatus"))
            )
            status_texto = status_elem.text.strip()
            
            if "novo registro" in status_texto.lower():
                return True
            
            return False
                
        except Exception as ex:
            tentativas += 1
            if tentativas >= max_tentativas:
                logs.error("clicar_new_rerserva - ", str(ex))
                return "Erro ao clicar em inculir nova reserva;", [], []
    

def corrigir_campos_vermelhos(driver_mapfre, valores_formulario):
    try:
        campos_em_vermelho = driver_mapfre.find_elements(By.CSS_SELECTOR,
            "input[style*='background-color:#FFD2D2'], select[style*='background-color:#FFD2D2']")

        if not campos_em_vermelho:
            print("⚠️ Não encontrou campos em vermelho para corrigir.")
            return 
        
        lista_ids_campos_vermelho = [campo.get_attribute("id") for campo in campos_em_vermelho]
        
        for id in lista_ids_campos_vermelho:
            campo_id = id
            print("🟥 Corrigindo campo:", campo_id)
            if campo_id in valores_formulario:
                try:
                    valor = valores_formulario[campo_id]
                    form = WebDriverWait(driver_mapfre, 40).until(
                            EC.presence_of_element_located((By.ID, "uptPnlForm"))
                    )
                    wait_for_dom_stable(driver_mapfre)
                    elemento = WebDriverWait(driver_mapfre, 40).until(
                        EC.element_to_be_clickable((By.ID, campo_id))
                    )
                    wait_for_dom_stable(driver_mapfre)

                    if elemento.tag_name == "select":
                        elemento.clear()
                        elemento = WebDriverWait(driver_mapfre, 40).until(
                        EC.element_to_be_clickable((By.ID, campo_id))
                        )
                        select = Select(elemento)
                        select.select_by_value(valor)
                        elemento = WebDriverWait(driver_mapfre, 40).until(
                        EC.element_to_be_clickable((By.ID, campo_id))
                        )
                        elemento.send_keys(Keys.TAB)
                    else:
                        elemento.clear()
                        elemento = WebDriverWait(driver_mapfre, 40).until(
                        EC.element_to_be_clickable((By.ID, campo_id))
                        )
                        elemento.send_keys(valor)
                        elemento = WebDriverWait(driver_mapfre, 40).until(
                        EC.element_to_be_clickable((By.ID, campo_id))
                        )
                        elemento.send_keys(Keys.TAB)  
                except Exception as e:
                    logs.warning(f"Falha ao corrigir campo {campo_id}: {e}")
                    print(f"⚠️ Falha ao corrigir campo {campo_id}: {e}")

        try:
            form_licitacao = WebDriverWait(driver_mapfre, 40).until(
                EC.presence_of_element_located((By.ID, "uptPnlForm"))
            )
            botao_gravar = WebDriverWait(driver_mapfre, 40).until(
                EC.element_to_be_clickable((By.ID, "btnUpdate"))
            )
            botao_gravar.click()  
            WebDriverWait(driver_mapfre, 20).until(EC.staleness_of(botao_gravar))
        except Exception as e:
                logs.warning(f"Erro ao clicar em Gravar: {e}")
                print(f"⚠️ Erro ao clicar em Gravar: {e}")
    except Exception as e:
        logs.warning(f"ERRO corrigir_campos_vermelhos: {e}")
        print(f"⚠️ corrigir_campos_vermelhos: {e}")

def aguardar_e_corrigir_status(driver_mapfre, valores_formulario):
    tentativas = 0
    max_tentativas=20
    while tentativas < max_tentativas:
        try:
            status_elem = WebDriverWait(driver_mapfre, 20).until(
                EC.element_to_be_clickable((By.ID, "lblStatus"))
            )
            time.sleep(1)
            status_texto = status_elem.text.strip().lower()

            if "em menos de 10 segundos" in status_texto:
                print("⏳ Mensagem 'em menos de 10 segundos' detectada, aguardando e tentando gravar novamente...")
                time.sleep(1)
                botao_gravar = WebDriverWait(driver_mapfre, 20).until(
                    EC.element_to_be_clickable((By.ID, "btnUpdate"))
                )
                time.sleep(0.5)
                driver_mapfre.execute_script("arguments[0].focus(); arguments[0].click();", botao_gravar)
                time.sleep(1)
                WebDriverWait(driver_mapfre, 20).until(EC.staleness_of(botao_gravar))

            elif "vermelho" in status_texto or "menor que 25 dígitos" in status_texto:
                print(f"⚠️ Detectado campos em vermelho. Tentando corrigir...")
                corrigir_campos_vermelhos(driver_mapfre, valores_formulario)

            else:
                return status_texto
            
            tentativas += 1
            
        except Exception as e:
            tentativas += 1
            if tentativas >= max_tentativas:
                logs.warning(f"ERRO aguardar_e_corrigir_status: {e}")
                print(f"⚠️ ERRO PARA aguardar_e_corrigir_status: {e}")
                
    print(f"⚠️ Número máximo de tentativas ({max_tentativas}) alcançado.")
    return status_texto   
    
def preencher_form_licitacao(driver_mapfre, edital, thread_download):
    try:
        links =[]
        msg = ""
        imgs = []
        url_arquivo_digital =  configuracoes.get("mafre", {}).get("url_arquivo_digital")
        url_anterior = driver_mapfre.current_url
        
        ramos_valores = edital.get("ramos_valores", []) 
        if isinstance(ramos_valores, str):
            ramos_valores = [ramos_valores]
            
        if not ramos_valores:
            logs.warning("Nenhum ramo identificado no objeto: '%s' | Link: %s", edital.get("objeto", ""), edital.get("Link", ""))
            msg += f"Edital nao Cadastrado (Ramo nao detectado);"
            return msg , links, imgs
        
        # Ajuste nos ramos 2 e 3 com base na capital
        if any(ramo in {"2", "3"} for ramo in ramos_valores):
            orgao = remover_acentos(edital.get("Orgao", "").upper())
            if "MUNICIPIO" in orgao or "CAMARA MUNICIPAL" in orgao:
                if any(capital in orgao for capital in CAPITAIS):
                    ramos_valores = ["3", "2"]
                else:
                    ramos_valores = ["3"]
            else:
                ramos_valores = ["2"]
        
        # Calcular valor da modalidade com regra especial
        licitacao = re.sub(r'\s*-\s*', ' ', edital.get("Licitacao", "")).strip().upper()
        if "DISPENSA" in licitacao:
            modalidade_valor = "DISPENSA ELETRÔNICA"
        else:
            modalidade_valor = licitacao
            
        uf_sigla = edital.get("Uf", "").strip().upper()
        territorial_valor = mapeamento_territorial.get(uf_sigla, "")


        # Mapeamento centralizado dos valores de preenchimento
        valores_formulario = {
            "idsolicitante_txtDescript": "R.B.GNP",
            "idcorretor_txtDescript": "GNP CORRETORA DE SEGUROS",
            "idterritorial_txtDescript": territorial_valor,
            "modalidade": modalidade_valor,
            "dataabertura": edital.get("DataFim", ""),
            "edital": edital.get("Numero", ""),    
        }
        
        for i, ramo in enumerate(ramos_valores):
            nome_ramo = NOMES_RAMO.get(ramo, f"Ramo {ramo}")
           
            if i > 0:
                driver_mapfre.get(url_anterior)
                status = clicar_new_rerserva(driver_mapfre)
                if status:
                    print("🔁 Nova reserva aberta:", status_texto)
                else:
                    msg = f"Erro ao tentar incluir nova reserva para o ramo:{ramo};"
                    continue
            try: 
                form_licitacao = WebDriverWait(driver_mapfre, 40).until(
                    EC.presence_of_element_located((By.ID, "uptPnlForm"))
                )
    
                ramo_elemento = form_licitacao.find_element(By.ID, "idramo")
                select_ramo = Select(ramo_elemento)
                select_ramo.select_by_value(ramo)
                
                if ramo == '6':
                    form_ramo= WebDriverWait(driver_mapfre, 40).until(
                        EC.presence_of_element_located((By.ID, "uptPnlForm"))
                    )
                    produto = form_ramo.find_element(By.ID, "cmbProduto")
                    select_produto = Select(produto)
                    select_produto.select_by_value("1") # 1 = APC
                
                for campo_id, valor in valores_formulario.items():
                    if campo_id == "edital" and modalidade_valor == "DISPENSA":
                        continue  # pula o campo 'edital' se for dispensa
                    try:
                        form = WebDriverWait(driver_mapfre, 40).until(
                            EC.presence_of_element_located((By.ID, "uptPnlForm"))
                        )
                        wait_for_dom_stable(driver_mapfre)
                        elemento = WebDriverWait(driver_mapfre, 40).until(
                            EC.element_to_be_clickable((By.ID, campo_id))
                        )
                        wait_for_dom_stable(driver_mapfre)
                        if elemento.tag_name == "select":
                            try:
                                select = Select(elemento)
                                select.select_by_value(valor)
                                elemento = WebDriverWait(driver_mapfre, 40).until(
                                    EC.presence_of_element_located((By.ID, campo_id))
                                )
                                driver_mapfre.execute_script("""
                                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                                """, elemento)
                                wait_for_dom_stable(driver_mapfre)
                            except:
                                elemento2 =  WebDriverWait(driver_mapfre, 40).until(
                                    EC.element_to_be_clickable((By.ID, campo_id))
                                )
                                driver_mapfre.execute_script("""
                                    let select = arguments[0];
                                    let value = arguments[1];
                                    for (let i = 0; i < select.options.length; i++) {
                                        if (select.options[i].value === value) {
                                            select.selectedIndex = i;
                                            break;
                                        }
                                    }
                                    var evt = new Event('change', { bubbles: true });
                                    select.dispatchEvent(evt);
                                """, elemento2, valor)
                                wait_for_dom_stable(driver_mapfre)
                        else:
                            try:
                                if modalidade_valor == "DISPENSA ELETRÔNICA":
                                    elemento.clear()
                                    
                                elemento = WebDriverWait(driver_mapfre, 20).until(
                                    EC.element_to_be_clickable((By.ID, campo_id))
                                )
                                driver_mapfre.execute_script("arguments[0].focus();", elemento)
                                elemento.send_keys(valor)
                                elemento = WebDriverWait(driver_mapfre, 20).until(
                                    EC.element_to_be_clickable((By.ID, campo_id))
                                )
                                driver_mapfre.execute_script("""
                                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                                """, elemento)
                                wait_for_dom_stable(driver_mapfre)
                            except:
                                elemento2 = WebDriverWait(driver_mapfre, 20).until(
                                    EC.element_to_be_clickable((By.ID, campo_id))
                                )
                                driver_mapfre.execute_script("arguments[0].value = arguments[1];", elemento2, valor)
                                driver_mapfre.execute_script("""
                                    var evt = document.createEvent('HTMLEvents');
                                    evt.initEvent('change', true, true);
                                    arguments[0].dispatchEvent(evt);
                                """, elemento2)
                                wait_for_dom_stable(driver_mapfre)
                                                        
                    except Exception as e:
                        print(f"Campo {campo_id} não preenchido: {e}")
                        logs.warning(f"Campo {campo_id} não preenchido: {e}")

                form_licitacao = WebDriverWait(driver_mapfre, 40).until(
                    EC.presence_of_element_located((By.ID, "uptPnlForm"))
                )
                botao_gravar = form_licitacao.find_element(By.ID, "btnUpdate")
                botao_gravar.click()  
                # Aguarda a resposta do sistema (o postback)
                WebDriverWait(driver_mapfre, 20).until(EC.staleness_of(botao_gravar))
                
                status_texto = aguardar_e_corrigir_status(driver_mapfre, valores_formulario)
                
                if "reserva validada para o canal corretor" in status_texto:
                    match = re.search(r"n[uú]mero\s*(\d+)", status_texto)
                    if match:
                        id_reserva = match.group(1)    
                        url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)
                        links.append(url_arquivo)
                        try:
                            # Aguarda a mensagem aparecer
                            WebDriverWait(driver_mapfre, 15).until(
                                EC.presence_of_element_located((By.ID, "dvMessageM"))
                            )

                            # Aguarda o botão ficar clicável
                            btn_ok = WebDriverWait(driver_mapfre, 15).until(
                                EC.element_to_be_clickable((By.ID, "aggerMessageM_btnOk"))
                            )

                            # Faz múltiplas tentativas de clique até garantir que desapareceu
                            for _ in range(3):
                                try:
                                    btn_ok.click()
                                    # Aguarda desaparecer
                                    WebDriverWait(driver_mapfre, 5).until(
                                        EC.invisibility_of_element_located((By.ID, "dvMessageM"))
                                    )
                                    break  # Se sumiu, sai do loop
                                except:
                                    time.sleep(0.8)
                        except Exception as ex:
                            pass  
                            
                        try:
                            WebDriverWait(driver_mapfre, 5).until(
                                EC.invisibility_of_element_located((By.ID, "dvMessageM"))
                            )
                            img = WebDriverWait(driver_mapfre, 40).until(
                                EC.presence_of_element_located((By.ID, "dvMessage"))
                            )  
                            print_img = WebDriverWait(driver_mapfre, 40).until(
                                EC.presence_of_element_located((By.CLASS_NAME, "blckControls"))
                            )          
                            path_img_reserva = f"reserva_img_{id_reserva}.png"
                            print_img.screenshot(path_img_reserva)          
                            imgs.append(path_img_reserva)
                        except Exception as ex:
                            print("Erro ao tirar print reserva perdida - ", str(ex))
                            logs.error(f"Erro ao tirar print reserva perdida - {ex}")
                            msg += f"Erro ao tentar tirar print reserva pertida;"
                            pass
                        
                        msg += f"Reserva já cadastrada reserva: {id_reserva}, ramo: {ramo}, CNPJ: {edital['Cnpj']};" 
                        print(f"⚠️ Já existe reserva cadastrada: {id_reserva}")
                        logs.warning("Reserva já cadastrada para o número %s - Link: %s", id_reserva, edital.get("Link", ""))

                    if len(ramos_valores) > 1:
                        print("🔁 Tentando próximo ramo...")
                        continue  
                    else:
                        return msg, links, imgs
                elif "sucesso" in status_texto:
                    id_reserva_elem = WebDriverWait(driver_mapfre, 20).until(
                        EC.presence_of_element_located((By.ID, "idlicitacao"))
                    )
                    id_reserva = id_reserva_elem.get_attribute("value")
                    
                    url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)  
                    links.append(url_arquivo)
                    driver_mapfre.get(url_arquivo)

                    if thread_download:
                        thread_download.join()  # Garante que o download terminou antes de anexar

                    msg += anexar_arquivos_mafre(driver_mapfre, edital)     
                    msg += f"Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};"
                    print(f"Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};")
                    logs.warning(f"Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};")
                else:
                    msg += f"Erro: {status_texto};"
    
            except Exception as ex:
                print("erro ao gravar reserva - ", str(ex))
                logs.error(f"Erro ao gravar reserva - {ex}")
                if len(ramos_valores) > 1:
                    print("🔁 Tentando próximo ramo...")
                    
                    msg += f"Erro ao gravar reserva no Mapfre para o ramo:{nome_ramo}, no edital CNPJ: {edital['Cnpj']}, Link: {edital['Link']};"
                    continue # volta para o próximo ramo
                else:
                    msg += f"Erro ao gravar reserva no Mapfre para o ramo:{nome_ramo}, no edital CNPJ: {edital['Cnpj']}, Link: {edital['Link']};"
                    return msg, "", []
                
        if not links:
            msg += f"Nenhum ramo foi cadastrado com sucesso;"
            return msg, links, imgs
        
        return msg, links, imgs
    
    except Exception as ex:
        logs.error(f"preencher_form_licitacao - {ex}")
        return "Erro ao preenchr formulário;", links, []
        
def anexar_arquivos_mafre(driver_mapfre, edital):
    try:
        caminho_arquivos = edital.get("pasta_edital_original", "")
        palavras_arquivos_exececoes = configuracoes.get("mafre", {}).get("palavras_arquivos_exececoes", [])

        if not caminho_arquivos:
            logs.warning(f"Caminho dos arquivos em branco para o edital: {edital.get('Link', '')}")
            return f"Caminho dos arquivos em branco para o edital: {edital.get('Link', '')};"

        arquivos = [
            f for f in os.listdir(caminho_arquivos)
            if os.path.isfile(os.path.join(caminho_arquivos, f))
        ]

        if not arquivos:
            logs.warning(f"Diretório sem arquivos: {caminho_arquivos} - Link: {edital.get('Link', '')}")
            return f"Nenhum arquivo encontrado em: {caminho_arquivos} - Edital: {edital.get('Link', '')};"

        WebDriverWait(driver_mapfre, 20).until(
            EC.presence_of_all_elements_located((By.ID, "uptPnlForm"))
        )
        botao_escolher_arquivos = WebDriverWait(driver_mapfre, 20).until(
            EC.element_to_be_clickable((By.ID, "fUpload"))
        )

        caminho_item = None

        if len(arquivos) > 1:
            for item in arquivos:
                if "edital" in item.lower():
                    caminho_item = os.path.join(caminho_arquivos, item)
                    break
                elif not any(p in item.lower() for p in palavras_arquivos_exececoes or []):
                    caminho_item = os.path.join(caminho_arquivos, item)
                    break
        else:
            caminho_item = os.path.join(caminho_arquivos, arquivos[0])

        if not caminho_item:
            return "Nenhum arquivo válido encontrado para envio;"

        botao_escolher_arquivos.send_keys(caminho_item)

        send_file = WebDriverWait(driver_mapfre, 20).until(
            EC.element_to_be_clickable((By.ID, "btnSendFile"))
        )
        driver_mapfre.execute_script("arguments[0].focus(); arguments[0].click();", send_file)

        status_elem = WebDriverWait(driver_mapfre, 20).until(
            EC.presence_of_element_located((By.ID, "lblStatus"))
        )
        status_texto = status_elem.text.strip()

        if "sucesso" in status_texto.lower():
            data_inclusao_arquivo_element = WebDriverWait(driver_mapfre, 20).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/form/div[3]/div/table[2]/tbody/tr[5]/td/div/table/tbody/tr[2]/td[7]"))
            )
            
            data_inclusao_arquivo = data_inclusao_arquivo_element.text.strip()
            return f"Sucesso ao gravar anexo, data inclusao: {data_inclusao_arquivo};"
        else:
            return status_texto

    except Exception as ex:
        logs.error("anexar_arquivos_mafre - Erro: %s", str(ex))
        return "Erro ao anexar arquivos caiu no except;"
    
def detectar_ramos(objeto_texto):
    texto = remover_acentos(objeto_texto.upper())
    encontrados = set()
    
    for value, palavras in RAMOS.items():
        for palavra in palavras:
            palavra_normalizada = remover_acentos(palavra.upper())
            pattern = r"\b{}\b".format(re.escape(palavra_normalizada))
            if re.search(pattern, texto):
                encontrados.add(value)
                break  # Evita duplicidade do mesmo ramo
    return encontrados

def validar_criar_reserva(edital):
    try:
        data_fim = edital.get("DataFim", "")
        data_fim_dt = datetime.strptime(data_fim, "%d/%m/%Y")
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ramos_valores = detectar_ramos(edital.get("Descricao", ""))
        licitacao = edital.get("Licitacao", "").upper()
        
        if data_fim_dt < hoje:
            logs.warning("Data Abertura é menor que dia atual: '%s' | Link: %s", data_fim, edital.get("Link", ""))
            return False, f"Data Abertura é menor que dia atual", []
        elif not any(modal in licitacao for modal in ["DISPENSA", "PREGÃO - ELETRÔNICO", "PREGÃO - PRESENCIAL"]):
            logs.warning("Modalidade não é valida para reserva : '%s' | Link: %s", licitacao, edital.get("Link", ""))
            return False, f"Modalidade não é valida para reserva ", []
        elif not ramos_valores:
            logs.warning("Nenhum ramo identificado no objeto: '%s' | Link: %s", edital.get("objeto", ""), edital.get("Link", ""))
            return False, f"Nenhum ramo identificado no objeto deste edital", []
        elif '6' in ramos_valores:
            valor_estimado_str = edital.get("ValorTotalEstimadoCompra", "")
            valor_estimado = limpar_valor(valor_estimado_str)
            qtde_itens = int(edital.get("QuantidadeItens", 0))
            valido = False
            if valor_estimado == "SIGILOSO" and qtde_itens > 100:
                valido = True
            elif isinstance(valor_estimado, (int, float)) and valor_estimado >= 3600:
                valido = True

            if not valido:
                if set(ramos_valores) == {'6'}:
                    return False, "Ramo VIDA não atende aos critérios e é o único ramo", []
                else:
                    ramos_valores = [r for r in ramos_valores if r != '6']
       
        return True, "", ramos_valores   
 
    except Exception as ex:
        logs.error("validar_criar_reserva - Erro: %s", str(ex))
        return "Erro ao validar reserva se atende requisitos, caiu no except"  


  
RAMOS = {
    # AERONÁUTICO
    "5": ["AERONÁUTICO", "DRONE"],
    # AERONÁUTICO CASCO
    "24": ["CASCO", "AERONÁUTICO CASCO", "DRONE e CASCO"],
    # AERONÁUTICO RETA
    "23": ["RETA", "R.E.T.A", "AERONÁUTICO e R.E.T.A", "DRONE e R.E.T.A"],
    # AUTOMÓVEIS
    "1": ["FROTA", "CARRO","VEICULO","VEICULOS","VEICULAR", "AUTOMOTIVO", "AUTOMOVEL", "AUTOMOVEIS", "AMBULANCIA",
          "SAMU", "ÔNIBUS", "VANS", "CAMINHÃO", "VIATURA", "VIATURAS","COMPREENSIVA", "COMPREENSIVO", "RCF", " RCO", "MAQUINA", "MÁQUINA"],
    # CASCO MARÍTIMO-EMBARCAÇÃO
    "20": ["MARÍTIMO", "BARCO", "EMBARCAÇÃO"],
    # DIFERENCIADOS (> 30 MI)
    "2": ["PRÉDIOS", "PREDIAL", "PATRIMONIAL", "PATRIMÔNIO", "PATRIMONIAIS", "EMPRESARIAL","IMÓVEL", "IMÓVEIS","EDIFÍCIO",
          "IMOBILIÁRIO", "LOCAL", "LOCAIS"],
    # MÁQUINAS E EQUIPAMENTOS
    "25": ["MAQUINA", "EQUIPAMENTO", "EQUIPAMENTOS", "TRATOR", "ESCAVADEIRA","ROLO COMPACTADOR", "RETROESCAVADEIRA", "PATROLA"],
    # MASSIFICADOS (< 30 MI)
    "3": ["PRÉDIOS", "PREDIAL", "PATRIMONIAL", "PATRIMÔNIO", "PATRIMONIAIS", "EMPRESARIAL","IMÓVEL", "IMÓVEIS", "EDIFÍCIO",
          "IMOBILIÁRIO", "LOCAL", "LOCAIS" ],
    # RESPONSABILIDADE CIVIL
    "9": ["RESPONSABILIDADE CIVIL"],
    # VIDA
    "6": ["VIDA", "PESSOAIS", "COLETIVO", "ACIDENTES", "ESTAGIÁRIOS", "ESTÁGIO","ESTUDANTES", "ALUNO", "FUNERAL"],
    #D&O
    "27": ["D&O"]
}

CAPITAIS = [
    "RIO BRANCO", "MACAPA", "MANAUS", "BELEM", "PORTO VELHO", "BOA VISTA", "PALMAS",
    "MACEIO", "SALVADOR", "FORTALEZA", "SAO LUIS", "JOAO PESSOA", "RECIFE", "TERESINA",
    "NATAL", "ARACAJU", "BRASILIA", "GOIANIA", "CUIABA", "CAMPO GRANDE", "VITORIA",
    "BELO HORIZONTE", "RIO DE JANEIRO", "SAO PAULO", "CURITIBA", "FLORIANOPOLIS", "PORTO ALEGRE"
]

# Mapeamento centralizado de UF para Territorial
mapeamento_territorial = {
    "DF": "CENTRO OESTE",
    "GO": "CENTRO OESTE",
    "MT": "CENTRO OESTE",
    "MS": "CENTRO OESTE",
    "MG": "MINAS GERAIS",
    "AC": "NORTE E NORDESTE",
    "AL": "NORTE E NORDESTE",
    "AP": "NORTE E NORDESTE",
    "AM": "NORTE E NORDESTE",
    "BA": "NORTE E NORDESTE",
    "CE": "NORTE E NORDESTE",
    "MA": "NORTE E NORDESTE",
    "PA": "NORTE E NORDESTE",
    "PB": "NORTE E NORDESTE",
    "PE": "NORTE E NORDESTE",
    "PI": "NORTE E NORDESTE",
    "RN": "NORTE E NORDESTE",
    "RO": "NORTE E NORDESTE",
    "RR": "NORTE E NORDESTE",
    "SE": "NORTE E NORDESTE",
    "TO": "NORTE E NORDESTE",
    "PR": "PARANA",
    "ES": "RIO DE JANEIRO",
    "RJ": "RIO DE JANEIRO",
    "RS": "RIO GRANDE DO SUL",
    "SC": "RIO GRANDE DO SUL",
    "SP": "SÃO PAULO CAPITAL",
}