# Imports da biblioteca padrão
from collections import OrderedDict
import os
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Imports de módulos locais
from funcoespncp import *
from gerar_planilha import *
from repositoriopncp import *
from drivers import *
from selenium.webdriver.support.ui import WebDriverWait
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import imgkit
import certifi
import urllib3

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
                    print("🔁 Senha expirada, mas login continuará após troca.")
                    trocar_senha(driver_mapfre, password)
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
                return "Erro ao processar trocar senha;", ""
   
def extrair_campos_hidden(html):
    """Extrai todos os campos hidden da página (VIEWSTATE, EVENTVALIDATION, etc.)"""
    soup = BeautifulSoup(html, "html.parser")
    campos = {}
    for campo in soup.find_all("input", type="hidden"):
        campos[campo.get("name")] = campo.get("value", "")
        
def fazer_post(session, url, pagina_html, botao_nome, campos_extra=None):
    """
    Simula clique em botão ASP.NET reaproveitando viewstate e outros hidden fields
    """
    campos = extrair_campos_hidden(pagina_html)
    if campos_extra:
        campos.update(campos_extra)
    campos[botao_nome] = ""  # Botão clicado (valor vazio normalmente)
    
    resp = session.post(url, data=campos)
    resp.raise_for_status()
    return resp.text

def pegar_hidden(texto, nome_campo):
    for bloco in texto.split('|'):
        # vamos pegar o próximo elemento após encontrar o nome
        # mas primeiro precisamos iterar pelos grupos
        partes = texto.split('|')
        for i in range(len(partes)):
            if partes[i] == nome_campo:
                return partes[i+1]  # o valor correto vem logo depois
    return None
   
def processar_pesquisa_licitacao(driver_mapfre, edital, thread_download):
    try: 
        links =[]
        msg = ""
        imgs = []
        url_pos_login = configuracoes.get("mafre", {}).get("url_pos_login")
        horario_inicio = datetime.now().strftime("%H:%M:%S")
        logs.warning(f">>>>>Entrou para processar mapfre: {horario_inicio}<<<<<<")
        cnpj_pesquisa = cnpj_formatado(edital.get("Cnpj", ""))
        cookies_list = driver_mapfre.get_cookies()
        cookies = {c['name']: c['value'] for c in cookies_list}
        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest"
        }

        soup_pos_login, info_pos_login = processar_requests_get(url_pos_login, cookies, headers)
        
        if info_pos_login:
            msg += f"Erro info_incluir:{info_pos_login}"
            
        viewstate = soup_pos_login.find(id="__VIEWSTATE")["value"]
        viewstategenerator = soup_pos_login.find(id="__VIEWSTATEGENERATOR")["value"]
        eventvalidation = soup_pos_login.find(id="__EVENTVALIDATION")["value"]
        
        # POST do filtro de CNPJ
        data_filter = { 
            "__VIEWSTATE": viewstate, 
            "__VIEWSTATEGENERATOR": viewstategenerator, 
            "__EVENTVALIDATION": eventvalidation, 
            "__ASYNCPOST": "true", 
            "ScriptManager1": "UpdatePanel|btnFilter", 
            "cmbFilter": 
            "cpf_cnpj", 
            "txtFilter": cnpj_pesquisa, 
            "btnFilter": "Filtrar", 
        }

        soup_filter, r_filter, info_filter = processar_resquests_post(url_pos_login, cookies, headers, data_filter)
        
        if info_filter:
            msg += f"Erro info_filter:{info_filter}"
                
        texto = r_filter.text 
        viewstate = pegar_hidden(texto, "__VIEWSTATE")
        viewstategenerator = pegar_hidden(texto, "__VIEWSTATEGENERATOR")
        eventvalidation = pegar_hidden(texto, "__EVENTVALIDATION")

        tabela = soup_filter.find(id="grdCliente")
        
        if not tabela:
            print("CNPJ não encontrado ou tabela não carregou.") 
            return "Erro CNPJ não encontrado ou tabela não carregou;", [], []
        
        cnpj_encontrado = tabela.find_all("tr")[1].find_all("td")[4].text.strip() 
        idCliente = tabela.find_all("tr")[1].find_all("td")[1].text.strip()
        nomeCliente = tabela.find_all("tr")[1].find_all("td")[2].text.strip()
        print(f"Valor do CNPJ pesquisa: {cnpj_pesquisa}")
        logs.warning(f"Valor do CNPJ pesquisa: {cnpj_pesquisa}")
        print(f"CNPJ encontrado: {cnpj_encontrado}, id cliente encontrado: {idCliente}, nome do cliente: {nomeCliente}")
        logs.warning(f"CNPJ encontrado: {cnpj_encontrado}, id cliente encontrado: {idCliente}, nome do cliente: {nomeCliente}")
        
        try: 
            # POST do filtro de CNPJ
            data_btn_licitacao = {
                "ScriptManager1": "UpdatePanel|btnLicitacao",
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__LASTFOCUS": "",
                "__VIEWSTATE": viewstate,
                "__VIEWSTATEGENERATOR": viewstategenerator,
                "__EVENTVALIDATION": eventvalidation,
                "__SCROLLPOSITIONX": "0",
                "__SCROLLPOSITIONY": "0",
                "cmbFilter": "cpf_cnpj",
                "txtFilter": cnpj_pesquisa,
                "cmbFilterAnalise": "idlicitacao",
                "txtFilterAnalise": "",
                "__ASYNCPOST": "true",
                "btnLicitacao": "Licitacao"
            }
 
            soup_filter_btn_licitacao, r_filter_btn_licitacao, info_btn_licitacao = processar_resquests_post(url_pos_login, cookies, headers, data_btn_licitacao)
         
            if info_btn_licitacao:
                msg += f"Erro info_btn_licitacao:{info_btn_licitacao}"
               
                
            match = re.search(r'pageRedirect\|\|(.*?)\|', r_filter_btn_licitacao.text)
            if match:
                url_redirect = match.group(1)
                url_form = urljoin(url_pos_login, url_redirect)
                msg, links, imgs = cadastro_licitacao_form(edital, driver_mapfre, thread_download, idCliente, url_form, cookies, headers)
            else:
                logs.error("Erro para redirecionamento de página para cadasto de reserva, pageRedirect nao encontrada; ", r_filter_btn_licitacao.text)
                return "Erro para redirecionamento de página para cadasto de reserva, pageRedirect nao encontrada;", [], []  
            
            return msg, links, imgs
        
        except Exception as ex:
            logs.error("Erro ao tentar clicar em reserva; ", str(ex))
            return "Erro ao tentar clicar em reserva;", [], []  
        
    except Exception as ex:
        logs.error("Erro ao tentar pesquisar cnpj; ", str(ex))
        return "Erro ao tentar pesquisar cnpj;", [], []
    

def cadastro_licitacao_form (edital, driver_mapfre, thread_download, idCliente, url_form, cookies, headers):
    try:
        links =[]
        msg = ""
        imgs = []
        url_arquivo_digital =  configuracoes.get("mafre", {}).get("url_arquivo_digital") 
        
        soup_link_form, info_link_form = processar_requests_get(url_form, cookies, headers) 
        if info_link_form:
            msg += f"Erro info_incluir:{info_link_form}"
        
        ramos_valores = edital.get("ramos_valores", [])    
        if isinstance(ramos_valores, str):
            ramos_valores = [ramos_valores]
        for i, ramo in enumerate(ramos_valores):
            tentativas = 0
            dez_segundos = False
            while True:
                uf_sigla = edital.get("Uf", "").upper()
                territorial_valor = mapeamento_territorial.get(uf_sigla, "")
                licitacao = edital.get("Licitacao", "").upper()
                modalidade_valor = "DISPENSA ELETRÔNICA" if "DISPENSA" in licitacao else ' '.join(licitacao.replace("-", " ").split())
                dataabertura = edital.get("DataFim", "")
                numero = edital.get("Numero", "")
                numero_formatado = numero.rjust(25, "0")  
                data_reserva = datetime.now().strftime("%d/%m/%Y")
                iddgt = "DC1"
                
                if territorial_valor in ["RIO GRANDE DO SUL", "SÃO PAULO CAPITAL", "PARANA"]:
                    iddgt = "DC1"
                elif territorial_valor in ["RIO DE JANEIRO", "NORTE E NORDESTE", "CENTRO OESTE", "MINAS GERAIS"]:
                    iddgt = "DC2"
                            
                texto_incluir, info_incluir = clicar_new_rerserva(soup_link_form, url_form, cookies, headers)
                
                if info_incluir:
                    msg += f"Erro info_incluir:{info_incluir}"
            
                viewstate = pegar_hidden(texto_incluir, "__VIEWSTATE")
                viewstategenerator = pegar_hidden(texto_incluir, "__VIEWSTATEGENERATOR")
                eventvalidation = pegar_hidden(texto_incluir, "__EVENTVALIDATION")
                
                dados_acumulados = OrderedDict([
                    ("ScriptManager", ""),
                    ("idlicitacao", "0"),
                    ("datareserva", data_reserva),
                    ("idcliente", idCliente),
                    ("idramo", ""),
                    ("idsolicitante$txtDescript", ""),
                    ("idcorretor$txtDescript", ""),
                    ("idsucursal$txtDescript", ""),
                    ("idterritorial$txtDescript", ""),
                    ("iddgt$txtDescript", ""),
                    ("modalidade", ""),
                    ("dataabertura", ""),
                    ("edital", ""),
                    ("idstatus", "2"),
                    ("cmbCotacao", "PENDENTE"),
                    ("cmbGarantia", "2"),
                    ("cmbStatusGarantia", "0"),
                    ("txtItemEdital", ""),
                    ("txtPercentualGarantido", ""),
                    ("observacao", ""),
                    ("txtValores", ""),
                    ("__EVENTTARGET", ""),
                    ("__EVENTARGUMENT", ""),
                    ("__LASTFOCUS", ""),
                    ("__VIEWSTATE", viewstate),
                    ("__VIEWSTATEGENERATOR", viewstategenerator),
                    ("__EVENTVALIDATION", eventvalidation),
                    ("__ASYNCPOST", "true"),
                ])
                
                campos = [
                    (["idramo"], [ramo]),
                    (["idsolicitante$txtDescript"], ["R.B.GNP"]),
                    (["idcorretor$txtDescript"], ["GNP CORRETORA DE SEGUROS"]),
                    (["idsucursal$txtDescript", "idterritorial$txtDescript"], 
                    ["SEM SUCURSAL - TODAS", territorial_valor]),  # par junto
                    (["iddgt$txtDescript", "modalidade"], 
                    [iddgt, modalidade_valor]),                    # par junto
                    (["dataabertura"], [dataabertura]),
                    (["edital"], [numero_formatado])
                ]
                
                if ramo == "6":
                        # Busca o índice do campo idsolicitante$txtDescript
                    for idx, (lista_campos, lista_valores) in enumerate(campos):
                        if "idsolicitante$txtDescript" in lista_campos:
                            # Adiciona cmbProduto = 1 nesse mesmo envio
                            campos[idx][0].insert(0, "cmbProduto")
                            campos[idx][1].insert(0, "1")
                            break
                        
                ASP_Net_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": "https://negociospublicos.mapfre.com.br",
                    "Referer": url_form,
                    "X-Requested-With": "XMLHttpRequest",
                    "X-MicrosoftAjax": "Delta=true",
                }
                horario_post_campo = datetime.now().strftime("%H:%M:%S")
                logs.warning(f">>>>>Entrou para enviar campo a campo em: {horario_post_campo}<<<<<<")
                # 5. Montar payload do formulário
                for lista_campos, lista_valores in campos:
                    for campo, valor in zip(lista_campos, lista_valores):
                        dados_acumulados[campo] = valor
                    
                    if ramo == "6" and "idsolicitante$txtDescript" in lista_campos:
                        items = list(dados_acumulados.items())
                        idx = list(dados_acumulados.keys()).index("idramo") + 1
                        items.insert(idx, ("cmbProduto", ""))
                        dados_acumulados = OrderedDict(items)
                    
                    campo_evento = lista_campos[-1]
                        
                    dados_acumulados["ScriptManager"] = f"uptPnlForm|{campo_evento}"
                    dados_acumulados["__EVENTTARGET"] = campo_evento
                    dados_acumulados["__VIEWSTATE"] = viewstate
                    dados_acumulados["__EVENTVALIDATION"] = eventvalidation
                     
                    soup_post_campo, r_post_campo, info_post_campo = processar_resquests_post(url_form, cookies, ASP_Net_headers, dados_acumulados,)
                    if info_post_campo:
                        msg += f"Erro soup_post_campo:{info_post_campo}"
                        
                    html = r_post_campo.text
                    viewstate = pegar_hidden(html, "__VIEWSTATE")
                    viewstategenerator = pegar_hidden(html, "__VIEWSTATEGENERATOR")
                    eventvalidation = pegar_hidden(html, "__EVENTVALIDATION")
                    
                    if None in (viewstate, viewstategenerator, eventvalidation):
                        msg += f"Erro ao enviar campo: {campo_evento}, CNPJ: {edital['Cnpj']}, status: {r_post_campo.text}; "
                        print(f"\nErro ao enviar campo: {campo_evento}, CNPJ: {edital['Cnpj']}, status: {r_post_campo.text}\n")
                        logs.warning(f"Erro ao enviar campo: {campo_evento}, CNPJ: {edital['Cnpj']}, status: {r_post_campo.text}")
                        return msg, [], []
                      
                dados_acumulados["ScriptManager"] = "uptPnlForm|btnUpdate"
                dados_acumulados["__EVENTTARGET"] = ""
                dados_acumulados["__VIEWSTATE"] = viewstate
                dados_acumulados["__VIEWSTATEGENERATOR"] = viewstategenerator
                dados_acumulados["__EVENTVALIDATION"] = eventvalidation
                dados_acumulados["btnUpdate"] = "Novo"
                
                if dez_segundos:
                    time.sleep(5)
                if tentativas > 0:
                    soup_post, r_post, lbl_status = None, None, None
                    
                time.sleep(2)
                horario_post = datetime.now().strftime("%H:%M:%S")
                logs.warning(f">>>>>Entrou para enviar o post em: {horario_post}<<<<<<")
                soup_post, r_post, info_post = processar_resquests_post(url_form, cookies, ASP_Net_headers, dados_acumulados)
                
                if info_post:
                    msg += info_post
                    
                horario_tmp = datetime.now().strftime("%H:%M:%S")
                logs.warning(f">>>>>Enviou o post em: {horario_tmp}<<<<<<")
                
                lbl_status = soup_post.find("span", id="lblStatus")
                if lbl_status:
                    status_texto = lbl_status.get_text(strip=True)       
                else:
                    msg += f"Erro ao fazer o post : {r_post.text};"
                    print(f"\n Erro ao fazer o post : {r_post.text} \n")
                    logs.warning(f"Erro ao fazer o post : {r_post.text}")
                    break
                
                if r_post.status_code != 200:
                    msg += f"Erro ao enviar formulario para o ramo: {ramo}, CNPJ: {edital['Cnpj']}, status: {r_post.status_code};"
                    print(f"\nErro ao enviar formulario para o ramo: {ramo}, CNPJ: {edital['Cnpj']}, status: {r_post.status_code} \n" )
                    logs.warning(f"Erro ao enviar formulario para o ramo: {ramo}, CNPJ: {edital['Cnpj']}, status: {r_post.status_code}" )
                    break
                
                if "Não é permitido gravar novas reservas em menos de 10 segundos." in status_texto:
                    print(" \n🔁 AVISO DE 10 SEGUNDOS PARA GRAVAR NOVA MENSAGEM... SERÁ FEITA NOVA TENTATIVA \n")
                    logs.warning(" \n >>>>AVISO DE 10 SEGUNDOS PARA GRAVAR NOVA MENSAGEM... SERÁ FEITA NOVA TENTATIVA<<<<<<< \n")
                    dez_segundos = True
                    tentativas += 1
                    continue
                
                if "vermelho" in status_texto or "menor que 25 dígitos" in status_texto:
                    print("\n🔁 AVISO DE CAMPOS EM VERMELHO OU NÚMERO EDITAL MENOR QUE 25 DÍGITOS... SERÁ FEITA NOVA TENTATIVA \n")
                    logs.warning(" \n >>>>AVISO DE CAMPOS EM VERMELHO OU NÚMERO EDITAL MENOR QUE 25 DÍGITOS... SERÁ FEITA NOVA TENTATIVA<<<<<<< \n")
                    tentativas += 1
                    continue
                    
                if "Registro gravado com sucesso..." in status_texto:
                    input_idlicitacao = soup_post.find("input", id="idlicitacao")
                    id_reserva = input_idlicitacao["value"] if input_idlicitacao and input_idlicitacao.has_attr("value") else None
                    
                    url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)  
                    links.append(url_arquivo)
                    driver_mapfre.get(url_arquivo)

                    if thread_download:
                        thread_download.join()  # Garante que o download terminou antes de anexar

                    msg += anexar_arquivos_mafre(driver_mapfre, edital, id_reserva)     
                    msg += f"Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};"
                    print(f"✅ Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};")
                    logs.warning(f"Sucesso ao cadastrar reserva para o ramo: {ramo}, reserva: {id_reserva};")
                    break
                    
                if "Já existe uma reserva validada para o canal Corretor sob o número" in status_texto:
                    match = re.search(r"n[uú]mero\s*(\d+)", status_texto)
                    if match:
                        id_reserva = match.group(1)    
                        url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)
                        links.append(url_arquivo)
                        
                        path_wkhtmltoimage = configuracoes.get("path_wkhtmltoimage")
                        config = imgkit.config(wkhtmltoimage=path_wkhtmltoimage)
                        
                        dv_message = soup_post.find("div", id="dvMessage")
                        if dv_message:
                            dv_html_str = str(dv_message)
                            # cria um soup a partir da string
                            dv_soup_img = BeautifulSoup(dv_html_str, "html.parser")
                                                            
                            for img in dv_soup_img.find_all("img"):
                                img["src"] = urljoin(url_form, img["src"])  # junta com a URL da página
                            
                            for tag in dv_soup_img.find_all(style=True):
                                style = tag["style"]
                                if "url(" in style:
                                    # substitui sysImagens/xxx pelo caminho absoluto
                                    style = style.replace("sysImagens/", "https://negociospublicos.mapfre.com.br/sysImagens/")
                                    tag["style"] = style 
                            
                            
                            html_message = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <style>
                                    body {{
                                        font-family: Arial, sans-serif;
                                    }}
                                    img {{
                                        max-width: 388px;
                                        max-height: 188px;
                                    }}
                                </style>
                            </head>
                            <body>
                                {str(dv_soup_img)}
                            </body>
                            </html>
                            """
                            
                            path_img_reserva = f"reserva_img_{id_reserva}.png"
                            success = imgkit.from_string(html_message, path_img_reserva, config=config)
                            
                            if success:
                                imgs.append(path_img_reserva)
                            else:
                                path_img_reserva = None
                                print("❌ Erro ao tirar print reserva perdida - ", str(ex))
                                logs.error(f"Erro ao tirar print reserva perdida - {ex}")
                                msg += f"Erro ao tentar tirar print reserva pertida;"
                                
                        msg += f"Reserva já cadastrada reserva: {id_reserva}, ramo: {ramo}, CNPJ: {edital['Cnpj']};" 
                        print(f"⚠️ Já existe reserva cadastrada: {id_reserva}")
                        logs.warning("Reserva já cadastrada para o número %s - Link: %s", id_reserva, edital.get("Link", ""))
                        break
                    
                if tentativas > 10:
                    msg += f"Erro Ramo {ramo} não conseguiu gravar após várias tentativas: {status_texto};"
                    print(f"Erro Ramo {ramo} não conseguiu gravar após várias tentativas: {status_texto}")
                    logs.warning(f"Erro Ramo {ramo} não conseguiu gravar após várias tentativas: {status_texto}")
                    break

        return msg, links, imgs
    
    except Exception as ex:
        logs.error("Erro ao tentar cadastrar licitacao; ", str(ex))
        return "Erro ao tentar cadastrar licitacao;", [], []

def processar_requests_get(url, cookies, headers):
    try:
        response_get = requests.get(url, cookies=cookies, headers=headers, timeout=15, verify=certifi.where())
        if response_get.status_code == 200:
            soup_get = BeautifulSoup(response_get.text, "html.parser")
            return soup_get, ""
        else:
            logs.error(f"Erro para pegara url no response:{response_get.text}")
            return response_get.text, "Erro para pegara url no response;"
    except requests.exceptions.Timeout:
        logs.error(f"Erro: processar_requests_get Timeout na requisição. O servidor demorou demais para responder.")
        return f"Erro: Timeout na requisição. O servidor demorou demais para responde;", [],[]
    except requests.exceptions.SSLError as ssl_err:
        logs.error(f"Erro SSL processar_requests_com_tratamento: {ssl_err}")
        return response_get.text, "Erro SSL;"
    except requests.exceptions.ConnectionError as conn_err:
        logs.error(f"Erro de conexão processar_requests_com_tratamento: {conn_err}")
        return response_get.text, "Erro de conexão;"
    except Exception as e:
        logs.error(f"Erro inesperado processar_requests_com_tratamento: {e}") 
        return response_get.text, "Erro inesperado;"
    
def processar_resquests_post(url, cookies, headers, data):
    try:
        response_post = requests.post(url, cookies=cookies, headers=headers, data= data,  timeout=15, verify=certifi.where())
        if response_post.status_code == 200:
            soup_post = BeautifulSoup(response_post.text, "html.parser")
            return soup_post, response_post, ""
        else:
            logs.error(f"Erro para pegara url no response:{response_post.text}")
            return f"Erro para pegara url no response;", response_post.text
    except requests.exceptions.Timeout:
        logs.error(f"Erro: Timeout na requisição. O servidor demorou demais para responder.")
        return response_post.text, "Erro: Timeout na requisição. O servidor demorou demais para responde;"
    except requests.exceptions.SSLError as ssl_err:
        logs.error(f"Erro SSL: {ssl_err}")
        return response_post.text, "Erro SSL;",response_post.text
    except requests.exceptions.ConnectionError as conn_err:
        logs.error(f"Erro de conexão: {conn_err}")
        return response_post.text, "Erro de conexão;", response_post.text
    except Exception as e:
        logs.error(f"Erro inesperado: {e}") 
        return response_post.text, "Erro inesperado; ",response_post.text

def clicar_new_rerserva(soup_final, url_form, cookies, headers):
    try:  
        viewstate = soup_final.find(id="__VIEWSTATE")["value"]
        viewstategenerator = soup_final.find(id="__VIEWSTATEGENERATOR")["value"]
        eventvalidation = soup_final.find(id="__EVENTVALIDATION")["value"]
            
        data_incluir = {
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstategenerator,
            "__EVENTVALIDATION": eventvalidation,
            "__ASYNCPOST": "true",
            "ScriptManager": "uptPnlForm|btnNew",
            "btnNew": "Novo",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": ""
        }
  
        soup_incluir , r_incluir, info = processar_resquests_post(url_form, cookies, headers, data_incluir)
        if r_incluir.status_code != 200:
            logs.error(f"Erro para clicar em incluir nova reservar:{r_incluir.text}")
            return r_incluir.text, info
        texto_incluir = r_incluir.text
        return texto_incluir, info
        
    except Exception as ex:
        logs.error("clicar_new_rerserva - ", str(ex))
        return "Erro ao clicar em inculir nova reserva;", [], [] 
  
def anexar_arquivos_mafre(driver_mapfre, edital, id_reserva):
    try:
        caminho_arquivos = edital.get("pasta_edital_original", "")
        palavras_arquivos_exececoes = configuracoes.get("mafre", {}).get("palavras_arquivos_exececoes", [])

        if not caminho_arquivos:
            logs.warning(f"Caminho dos arquivos em branco para o edital: {edital.get('Link', '')}, reserva: {id_reserva}")
            return f"Erro Caminho dos arquivos em branco para reserva: {id_reserva}"

        arquivos = [
            f for f in os.listdir(caminho_arquivos)
            if os.path.isfile(os.path.join(caminho_arquivos, f))
        ]

        if not arquivos:
            logs.warning(f"Diretório sem arquivos: {caminho_arquivos} - Link: {edital.get('Link', '')};")
            return f"Erro Nenhum arquivo encontrado em: {caminho_arquivos} reserva: {id_reserva}"

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
            return f"Nenhum arquivo válido encontrado para envio reserva: {id_reserva}"

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
            return f"Sucesso ao gravar anexo, data inclusao: {data_inclusao_arquivo}"
        else:
            return status_texto

    except Exception as ex:
        logs.error("anexar_arquivos_mafre - Erro: %s", str(ex))
        return "Erro ao anexar arquivos caiu no except; "

def detectar_ramos(objeto_texto):
    texto = remover_acentos(objeto_texto.upper())
    encontrados = set()
    
    for value, palavras in RAMOS.items():
        for palavra in palavras:
            palavra_normalizada = remover_acentos(palavra.upper())
            
            if value in RAMOS_COM_SEGURO:
                # aceita: "SEGURO VIDA", "SEGURO DE VIDA", "SEGURO PARA VIDA"
                pattern = r"\bSEGURO(?:\s+(?:DE|PARA))?\s+{}\b".format(re.escape(palavra_normalizada))
            else:
                # regra normal
                pattern = r"\b{}\b".format(re.escape(palavra_normalizada))
            
            if re.search(pattern, texto):
                encontrados.add(value)
                break  # evita duplicidade do mesmo ramo

    # regra especial do ramo 1 x 24
    if "1" in encontrados and "24" in encontrados:
        if not re.search(r"\bAERONAUTICO CASCO\b", texto) and not re.search(r"\bDRONE E CASCO\b", texto):
            encontrados.discard("24")
                   
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
        return "Erro ao validar reserva se atende requisitos, caiu no except;"  

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

# ramos que exigem "seguro de", "seguro para" ou "seguro X"
RAMOS_COM_SEGURO = {"2", "3", "6", "9"}