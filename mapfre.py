# Imports da biblioteca padrão
import os
import re
import shutil
from datetime import datetime
from os.path import isfile
import unicodedata
from unidecode import unidecode
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException, ElementClickInterceptedException
# Imports de módulos locais
from funcoespncp import *
from gerar_planilha import *
from repositoriopncp import *
from drivers import *

def inicializar_pagina_mafre(edital, mostrar_browser = False):
    try:
        print(f"\nExecutando Processo na Mafre pro edital: {edital["Link"]}\n") 
        msg = ""
        links = []
        url_login = configuracoes.get("mafre", {}).get("url_login")
        driver_mafre, profile_dir = criar_driver(mostrar_browser)
        driver_mafre.get(url_login)
        
        msg, links = processar_login_mafre(driver_mafre, edital)
        return msg, links
    
    except Exception as ex:
        logs.error("inicializar_pagina_mafre - ", str(ex))
        return "ERRO AO INICIALIZAR PAGINA MAFRE; ", "" 
    finally:
        if driver_mafre:
            encerrar_driver_com_timeout(driver_mafre) 
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)
    
   
def processar_login_mafre(driver_mafre, edital):
    try:
        msg = ""
        links = []
        
        user = configuracoes.get("mafre", {}).get("user")
        password = configuracoes.get("mafre", {}).get("password")
        
        controles_iniciais(driver_mafre)
        
        WebDriverWait(driver_mafre, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, "/html/body/form/div[3]/div/div/div[2]"))
        )

        usuario = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.XPATH, ".//table/tbody/tr[1]/td[2]/input"))
        )
        usuario.send_keys(user)

        senha = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.XPATH, ".//table/tbody/tr[2]/td[2]/input"))
        )
        senha.send_keys(password)

        botao_login = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "btnLogin"))
        )
        botao_login.click()
        
        try:
            WebDriverWait(driver_mafre, 40).until(
                EC.presence_of_element_located((By.ID, "btnConfirmaTermos"))
            )
            print("✅ Login bem-sucedido")
            msg, links = processar_pos_login(driver_mafre, edital)
            return msg, links 
           
        except:
            try:
                # Tenta verificar se a senha está expirada
                WebDriverWait(driver_mafre, 10).until(
                    EC.presence_of_element_located((By.ID, "lblFormTitle"))
                )
                trocar_senha(driver_mafre, password)

                print("🔁 Senha expirada, mas login continuará após troca.")
                msg, links = processar_pos_login(driver_mafre, edital)
                return msg, links

            except Exception:
                # Se não achou nenhum dos elementos esperados
                print("❌ Falha no login")
                return "Falha no login", ""

    except Exception as ex:
        logs.error("processar_login_mafre - ", str(ex))
        return "Erro ao processar login; ", ""
    

def trocar_senha(driver_mafre, password):
    try:
        WebDriverWait(driver_mafre, 20).until(
            EC.presence_of_all_elements_located((By.ID, "UpdatePanel"))
        )
        
        txtSenha = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "txtSenha"))
        )
        time.sleep(0.5)
        txtSenha.send_keys(password)
        time.sleep(0.5)
        txtNsenha = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "txtNsenha"))
        )
        time.sleep(0.5)
        txtNsenha.send_keys(password)
        time.sleep(0.5)
        txtCsenha = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "txtCsenha"))
        )
        time.sleep(0.5)
        txtCsenha.send_keys(password)
        time.sleep(0.5)
        botao_gravar = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "btnUpdate"))
        )
        time.sleep(0.5)
        botao_gravar.click()
        
    except Exception as ex:
        logs.error("trocar_senha - ", str(ex))
        return "Erro ao processar trocar senha; ", ""
        
def processar_pos_login(driver_mafre, edital):
    try:
        msg = ""
        links = []
        url_pos_login = configuracoes.get("mafre", {}).get("url_pos_login")
        driver_mafre.get(url_pos_login)
        
        wait = WebDriverWait(driver_mafre, 10)  # Espera até 10 segundos
        
        WebDriverWait(driver_mafre, 15).until(
            EC.presence_of_all_elements_located((By.ID, "UpdatePanel"))
        )
        
        filtro_pesquisa = WebDriverWait(driver_mafre, 15).until(
            EC.element_to_be_clickable((By.ID, "cmbFilter"))
        )
        select_filtro = Select(filtro_pesquisa)
        select_filtro.select_by_value("cpf_cnpj")
        valor_selecionado = select_filtro.first_selected_option.get_attribute("value")
        print("Filtro selecionado:", valor_selecionado)
        time.sleep(0.5)

        cnpj_pesquisa = cnpj_formatado(edital.get("Cnpj", ""))
        texto_pesquisa = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "txtFilter"))
        )
        time.sleep(0.5)
        texto_pesquisa.send_keys(cnpj_pesquisa)
        time.sleep(0.5)
        texto_pesquisa.send_keys(Keys.TAB)  

        # Aguarda o campo ser refletido corretamente com o valor esperado
        WebDriverWait(driver_mafre, 5).until(
            lambda d: d.find_element(By.ID, "txtFilter").get_attribute("value") != ""
        )
        # 5. (Opcional) Confirma o valor final para debug
        valor_input = driver_mafre.find_element(By.ID, "txtFilter").get_attribute("value")      
        print("Valor do cnpj pesquisa:", cnpj_pesquisa)
        print("Valor do input:", valor_input)

        for _ in range(2):
            try:
                time.sleep(1)
                botao_filter  = WebDriverWait(driver_mafre, 15).until(
                    EC.element_to_be_clickable((By.ID, "btnFilter"))
                )
                time.sleep(0.5)
                driver_mafre.execute_script("arguments[0].click();", botao_filter)
                time.sleep(0.8)
                break
            except (StaleElementReferenceException, ElementClickInterceptedException) as ex:
                logs.warning("Tentativa de clicar em btnFilter falhou: %s", ex)
                     
        try: 
            WebDriverWait(driver_mafre, 15).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/form/div[3]/div/table/tbody/tr[4]/td/div/table/tbody/tr[2]/td[5]'))
            )
            time.sleep(0.2)
            valor_input = driver_mafre.find_element(By.ID, "txtFilter").get_attribute("value")
            print("Valor no input depois do clique:", valor_input)

            time.sleep(0.2)
            valor_razao_social = driver_mafre.find_element(By.ID, "grdCliente_ctl02_lblRazaosocial").text
            print("Razao Social:", valor_razao_social)
            print("OGRAO:", edital.get("Orgao", ""))
            
            cnpj_elem = WebDriverWait(driver_mafre, 10).until(
                EC.presence_of_element_located((By.XPATH, '//table[@id="grdCliente"]/tbody/tr[2]/td[5]'))
            )
            time.sleep(0.5)
            cnpj_encontrado= cnpj_elem.text.strip()
            print("CNPJ encontrado:", cnpj_encontrado)
            
            botao_reserva = WebDriverWait(driver_mafre, 15).until(
                EC.element_to_be_clickable((By.ID, "btnLicitacao"))
            )
            time.sleep(0.5)
            driver_mafre.execute_script("arguments[0].click();", botao_reserva)
        
            status = clicar_new_rerserva(driver_mafre)
            
            if status:
                msg, links = preencher_form_licitacao(driver_mafre, edital)
            else:
                msg += "Erro ao tentar clicar em incluir reserva; "
            return msg, links 
               
        except Exception:
            print(f"❌ NÃO HÁ REGISTRO PARA ESSE CNPJ: {edital['Cnpj']}")
            return "NÃO HÁ REGISTRO PARA ESSE CNPJ; ", [] 
            
    except Exception as ex:
        logs.error("processar_pos_login - ", str(ex))
        return "Erro ao processar pagina pos login; ", []
    

def clicar_new_rerserva(driver_mafre):
    try:
        WebDriverWait(driver_mafre, 20).until(
            lambda d: d.find_element(By.ID, "btnNew").get_attribute("disabled") is None
        )
        time.sleep(0.5)
        botao = driver_mafre.find_element(By.ID, "btnNew")
        time.sleep(0.5)
        driver_mafre.execute_script("arguments[0].focus(); arguments[0].click();", botao)
        
        time.sleep(1)
        status_elem = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "lblStatus"))
        )
        status_texto = status_elem.text.strip()
        
        if "novo registro" in status_texto.lower():
            return True
        
        return False
            
    except Exception as ex:
        logs.error("clicar_new_rerserva - ", str(ex))
        return "Erro ao clicar em inculir nova reserva; ", []
    

def corrigir_campos_vermelhos(driver, valores_formulario, max_tentativas=3):
    tentativa = 0
    
    while tentativa < max_tentativas:
        status_elem = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "lblStatus"))
        )
        time.sleep(0.5)
        status_texto = status_elem.text.strip().lower()

        if not ("vermelho" in status_texto or "menor que 25 dígitos" in status_texto):
            return status_texto

        print(f"⚠️ Tentativa {tentativa+1} para corrigir campos em vermelho")

        campos_em_vermelho = driver.find_elements(By.CSS_SELECTOR,
            "input[style*='background-color:#FFD2D2'], select[style*='background-color:#FFD2D2']")

        if not campos_em_vermelho:
            print("⚠️ Não encontrou campos em vermelho para corrigir.")
            return status_texto
        
        lista_ids_campos_vermelho = [campo.get_attribute("id") for campo in campos_em_vermelho]
        
        for id in lista_ids_campos_vermelho:
            campo_id = id
            print("🟥 Corrigindo campo:", campo_id)
            if campo_id in valores_formulario:
                try:
                    valor = valores_formulario[campo_id]
                    elemento = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.ID, campo_id))
                    )
                    if elemento.tag_name == "select":
                        Select(elemento).select_by_value(valor)
                    else:
                        elemento.clear()
                        elemento.send_keys(valor)
                        elemento.send_keys(Keys.TAB)
                    time.sleep(0.5)
                except Exception as e:
                    logs.warning(f"Falha ao corrigir campo {campo_id}: {e}")
                    print(f"⚠️ Falha ao corrigir campo {campo_id}: {e}")

        try:
            botao_gravar = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "btnUpdate"))
            )
            time.sleep(0.5)
            driver.execute_script("arguments[0].focus(); arguments[0].click();", botao_gravar)
            time.sleep(1.5)
        except Exception as e:
                logs.warning(f"Erro ao clicar em Gravar: {e}")
                print(f"⚠️ Erro ao clicar em Gravar: {e}")
        
        tentativa += 1
     
    status_elem = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "lblStatus"))
    )
    time.sleep(0.5)
    return status_elem.text.strip().lower()
   
def preencher_form_licitacao(driver_mafre, edital):
    try:
        links =[]
        msg = ""
        url_arquivo_digital =  configuracoes.get("mafre", {}).get("url_arquivo_digital")
        url_anterior = driver_mafre.current_url
        
        WebDriverWait(driver_mafre, 40).until(
            EC.presence_of_element_located((By.ID, "uptPnlForm"))
        )

        ramo = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "idramo"))
        )
        select_ramo = Select(ramo)
        
        ramos_valores = edital.get("ramos_valores", []) 
        if isinstance(ramos_valores, str):
            ramos_valores = [ramos_valores]
            
        if not ramos_valores:
            logs.warning("Nenhum ramo identificado no objeto: '%s' | Link: %s", edital.get("objeto", ""), edital.get("Link", ""))
            msg += f"Edital nao Cadastrado (Ramo nao detectado); "
            return msg , links
        
        # Ajuste nos ramos 2 e 3 com base na capital
        if any(ramo in {"2", "3"} for ramo in ramos_valores):
            orgao = remover_acentos(edital.get("Orgao", "").upper())
            if "MUNICIPIO DE" in orgao or "CAMARA MUNICIPAL DE" in orgao:
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

        # Mapeamento centralizado dos valores de preenchimento
        valores_formulario = {
            "idsolicitante_txtDescript": "R.B.GNP",
            "idcorretor_txtDescript": "GNP CORRETORA DE SEGUROS",
            "idterritorial_txtDescript": "RIO GRANDE DO SUL",
            "modalidade": modalidade_valor,
            "dataabertura": edital.get("DataFim", ""),
            "edital": edital.get("Numero", ""),    
        }
        
        for i, ramo in enumerate(ramos_valores):
            if i > 0:
                driver_mafre.get(url_anterior)
                status = clicar_new_rerserva(driver_mafre)
                if status:
                    print("🔁 Nova reserva aberta:", status_texto)
                else:
                    msg = f"Erro ao tentar incluir nova reserva para o ramo:{ramo}; "
                    continue
            try: 
                select_ramo.select_by_value(ramo)
                
                if ramo == '6':
                    produto = WebDriverWait(driver_mafre, 20).until(
                        EC.element_to_be_clickable((By.ID, "cmbProduto"))
                    )
                    time.sleep(0.5)  
                    select_produto = Select(produto)
                    time.sleep(0.5)
                    select_produto.select_by_value("1") # 1 = APC
                
                for campo_id, valor in valores_formulario.items():
                    if campo_id == "edital" and modalidade_valor == "DISPENSA":
                        continue  # pula o campo 'edital' se for dispensa
                    try:
                        time.sleep(0.5)
                        elemento = WebDriverWait(driver_mafre, 20).until(
                            EC.element_to_be_clickable((By.ID, campo_id))
                        )
                        time.sleep(0.5)
                        if elemento.tag_name == "select":
                            driver_mafre.execute_script("""
                                arguments[0].value = arguments[1];
                                arguments[0].dispatchEvent(new Event('change'));
                            """, elemento, valor)
                            time.sleep(0.5)
                        else:
                            driver_mafre.execute_script("""
                                arguments[0].value = arguments[1];
                                arguments[0].dispatchEvent(new Event('change'));
                            """, elemento, valor)
                            time.sleep(0.5)    
                    except Exception as e:
                        print(f"Campo {campo_id} não preenchido: {e}")
                        logs.warning(f"Campo {campo_id} não preenchido: {e}")

                time.sleep(1)
                botao_gravar = WebDriverWait(driver_mafre, 20).until(
                    EC.element_to_be_clickable((By.ID, "btnUpdate"))
                )
                time.sleep(0.5)  
                driver_mafre.execute_script("arguments[0].focus(); arguments[0].click();", botao_gravar)
                time.sleep(0.5)   
                # Aguarda a resposta do sistema (o postback)
                WebDriverWait(driver_mafre, 20).until(EC.staleness_of(botao_gravar))
                
                # Usa o método para corrigir os campos em vermelho
                status_texto = corrigir_campos_vermelhos(driver_mafre, valores_formulario)
                    
                if "reserva validada para o canal corretor" in status_texto:
                    match = re.search(r"n[uú]mero\s*(\d+)", status_texto)
                    if match:
                        id_reserva = match.group(1)    
                        url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)
                        links.append(url_arquivo)
                        msg += f"Reserva já cadastrada: {url_arquivo}, RAMO: {ramo}, CNPJ: {edital['Cnpj']}; " 
                        print(f"⚠️ Já existe reserva cadastrada: {id_reserva}")
                        logs.warning("Reserva já cadastrada para o número %s - Link: %s", id_reserva, edital.get("Link", ""))

                    if len(ramos_valores) > 1:
                        print("🔁 Tentando próximo ramo...")
                        continue  
                    else:
                        return msg, links
                elif "sucesso" in status_texto:
                    id_reserva_elem = WebDriverWait(driver_mafre, 20).until(
                        EC.presence_of_element_located((By.ID, "idlicitacao"))
                    )
                    id_reserva = id_reserva_elem.get_attribute("value")
                    
                    url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)  
                    links.append(url_arquivo)
                    driver_mafre.get(url_arquivo)
                
                    msg += anexar_arquivos_mafre(driver_mafre, edital)     
                    msg += f"Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};"
    
            except Exception as ex:
                print("erro ao gravar reserva - ", str(ex))
                logs.error(f"Erro ao gravar v - {ex}")
                if len(ramos_valores) > 1:
                    print("🔁 Tentando próximo ramo...")
                    msg += f"Erro ao gravar reserva no Mapfre para o ramo:{ramo}, no edital CNPJ: {edital['Cnpj']}, Link: {edital['Link']}; "
                    continue # volta para o próximo ramo
                else:
                    msg += f"Erro ao gravar reserva; "
                    return msg, ""
                
        if not links:
            msg += f"Nenhum ramo foi cadastrado com sucesso.; "
            return msg, links
        
        return msg, links 
    
    except Exception as ex:
        logs.error(f"preencher_form_licitacao - {ex}")
        return "Erro ao preenchr formulário;", links

def fechar_mensagens_ok_generico(driver):
    while True:
        try:
            botao_ok = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(@id, 'btnOk')]"))
            )
            botao_ok.click()
            time.sleep(0.5)  
        except:
            break  
        
def anexar_arquivos_mafre(driver_mafre, edital):
    try:
        caminho_arquivos = edital.get("pasta_edital_original", "")
        palavras_arquivos_exececoes = configuracoes.get("mafre", {}).get("palavras_arquivos_exececoes", [])

        if not caminho_arquivos:
            logs.warning(f"Caminho dos arquivos em branco para o edital: {edital.get('Link', '')}")
            return f"Caminho dos arquivos em branco para o edital: {edital.get('Link', '')}\n"

        arquivos = [
            f for f in os.listdir(caminho_arquivos)
            if os.path.isfile(os.path.join(caminho_arquivos, f))
        ]

        if not arquivos:
            logs.warning(f"Diretório sem arquivos: {caminho_arquivos} - Link: {edital.get('Link', '')}")
            return f"Nenhum arquivo encontrado em: {caminho_arquivos} - Edital: {edital.get('Link', '')}\n"

        WebDriverWait(driver_mafre, 20).until(
            EC.presence_of_all_elements_located((By.ID, "uptPnlForm"))
        )
        botao_escolher_arquivos = WebDriverWait(driver_mafre, 20).until(
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
            return "Nenhum arquivo válido encontrado para envio.;"

        botao_escolher_arquivos.send_keys(caminho_item)

        send_file = WebDriverWait(driver_mafre, 20).until(
            EC.element_to_be_clickable((By.ID, "btnSendFile"))
        )
        driver_mafre.execute_script("arguments[0].focus(); arguments[0].click();", send_file)

        status_elem = WebDriverWait(driver_mafre, 20).until(
            EC.presence_of_element_located((By.ID, "lblStatus"))
        )
        status_texto = status_elem.text.strip()

        if "sucesso" in status_texto.lower():
            data_inclusao_arquivo_element = WebDriverWait(driver_mafre, 20).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/form/div[3]/div/table[2]/tbody/tr[5]/td/div/table/tbody/tr[2]/td[7]"))
            )
            
            data_inclusao_arquivo = data_inclusao_arquivo_element.text.strip()
            return f"Sucesso ao gravar anexo, data inclusao: {data_inclusao_arquivo}; "
        else:
            return status_texto

    except Exception as ex:
        logs.error("anexar_arquivos_mafre - Erro: %s", str(ex))
        return "Erro ao anexar arquivos caiu no except; "
    
def detectar_ramos(objeto_texto):
    texto = objeto_texto.upper()
    encontrados = set()
    
    for value, palavras in RAMOS.items():
        for palavra in palavras:
            pattern = r"\b{}\b".format(re.escape(palavra.upper()))
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
       
        return True, "", ramos_valores   
 
    except Exception as ex:
        logs.error("validar_criar_reserva - Erro: %s", str(ex))
        return "Erro ao validar reserva se atende requisitos, caiu no except"  


def remover_acentos(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')

RAMOS = {
    # AERONÁUTICO
    "5": ["AERONÁUTICO", "DRONE"],
    # AERONÁUTICO CASCO
    "24": ["CASCO", "AERONÁUTICO CASCO", "DRONE e CASCO"],
    # AERONÁUTICO RETA
    "23": ["RETA", "R.E.T.A", "AERONÁUTICO e R.E.T.A", "DRONE e R.E.T.A"],
    # AUTOMÓVEIS
    "1": ["FROTA", "CARRO", "VEÍCULO", "VEÍCULOS","VEICULAR", "VEÍCULAR", "AUTOMOTIVO", "AUTOMÓVEL", "AUTOMÓVEIS","AMBULÂNCIA", 
          "SAMU", "ÔNIBUS", "VANS", "CAMINHÃO", "VIATURA", "VIATURAS","COMPREENSIVA", "COMPREENSIVO", "RCF", " RCO", "MAQUINA"],
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
}

CAPITAIS = [
    "RIO BRANCO", "MACAPA", "MANAUS", "BELEM", "PORTO VELHO", "BOA VISTA", "PALMAS",
    "MACEIO", "SALVADOR", "FORTALEZA", "SAO LUIS", "JOAO PESSOA", "RECIFE", "TERESINA",
    "NATAL", "ARACAJU", "BRASILIA", "GOIANIA", "CUIABA", "CAMPO GRANDE", "VITORIA",
    "BELO HORIZONTE", "RIO DE JANEIRO", "SAO PAULO", "CURITIBA", "FLORIANOPOLIS", "PORTO ALEGRE"
]

