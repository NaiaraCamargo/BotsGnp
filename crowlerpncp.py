# Imports da biblioteca padrão
import math
import os
import re
import string
from threading import Thread
import time
import copy
import shutil
import locale
import zipfile
import mimetypes
import sqlite3
from pathlib import Path
from itertools import islice
from datetime import datetime
from os.path import isfile
import rarfile
import subprocess
# Imports de bibliotecas externas
import requests
import ghostscript
import pypandoc
from PIL import Image
from unidecode import unidecode
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from PyPDF2 import PdfReader, PdfWriter

# Imports de módulos locais
from funcoespncp import *
from gerar_planilha import *
from mapfre_aspnet import validar_criar_reserva, processar_pesquisa_licitacao, processar_login_mafre
from repositoriopncp import *
from drivers import *
from threading import Lock

lock_pos_login = Lock()
editais_em_processamento = set()
lock_editais = Lock()

retornoMsg = ""

class ControleMetadados:
    def __init__(self):
        if not isfile("metadados.db"):
            logs.info("Base metadados.db inexistente, criando arquivo...")
            f = open("metadados.db", "w")
            f.close()
            logs.info("Arquivo metadados.db criado com sucesso!")

        with sqlite3.connect("metadados.db") as conexao:
            logs.info("Verificando tabela metadados...")
            self.conexao = conexao
            self.cursor = conexao.cursor()
            self.cursor.execute("CREATE TABLE IF NOT EXISTS metadados (nome char(100), valor char(250));")
            self.conexao.commit()
            logs.info("Tabela metadados ok!")

    def retornar_valor(self):
        self.cursor.execute("SELECT valor FROM metadados WHERE nome = 'caminho_webdriver'")
        retorno = self.cursor.fetchone()
        if retorno is not None:
            return retorno[0]
        return None

    def atualizar_valor(self, novo_valor):
        self.cursor.execute("SELECT valor FROM metadados WHERE nome = 'caminho_webdriver'")
        retorno = self.cursor.fetchone()
        if retorno is not None:
            self.cursor.execute(f"UPDATE metadados SET valor = '{novo_valor}' WHERE nome = 'caminho_webdriver'")
        else:
            self.cursor.execute(f"INSERT INTO metadados VALUES('caminho_webdriver', '{novo_valor}')")
        self.conexao.commit()

metadados = ControleMetadados()


def carregar_filtros(nome, valores='', filtros_base=None):
    if filtros_base is None:
        filtros_base = {}

    if isinstance(nome, dict):
        for key_dic in nome:
            filtros_base[key_dic] = nome[key_dic]
    elif isinstance(nome, str):
        if nome not in filtros_base:
            filtros_base[nome] = {}

        if isinstance(valores, dict):
            filtros_base[nome] = valores
        else:
            for f in valores.split('|'):
                f = f.split("=")
                if len(f) == 1:
                    filtros_base[nome][f[0].strip()] = ""
                elif len(f) == 2:
                    filtros_base[nome][f[0].strip()] = f[1].strip()
    else:
        logs.error(f"Filtro não pode ser carregado - Nome: {str(nome)} - Valores: {str(valores)}")

    return filtros_base

  
def crawler(url, filtros='', notificacao_config='', mostrar_browser=False):
    id_pagina = notificacao_config['id_pagina']
    ids_usuarios = notificacao_config['ids_usuarios']
    plataforma = notificacao_config['plataforma']
    lista_elementos = []
    ultima_limpeza = time.time()

    try: 
        if url.strip() == "":
            logs.error("A URL está vazia")
            return
        
        filtros_base = carregar_filtros(filtros)
        url_base = url

        while True:
            hora_atual = datetime.now().hour
            processar_dia = configuracoes.get('processar_dia')
            controle_logs(f"{plataforma}-new")
            
            driver, profile_dir = None, None
           
            try:
                
                driver, profile_dir = criar_driver(mostrar_browser)
                acessar_url(driver, url_base, plataforma, processar_dia, hora_atual)
                
                lista_elementos.clear()
                total_processados = 0
                quantidade_para_processar = 0
                pagina = 2
                total_itens_tmp = 0

                print(f"\nIniciando processamento da página: {url}\n")
                processar_pagina(driver, url_base, filtros_base, id_pagina, ids_usuarios,lista_elementos, plataforma, total_processados, 
                    quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp, profile_dir)
                
                atualizar_ultima_data(id_pagina)
                filtros_base["banco"]["qtd_registros"] = retornar_registro_paginas(id_pagina, 4)

                #Limpar console a cada 10 minutos
                if time.time() - ultima_limpeza >= 600:
                    limpar_console()
                    carregar_configuracoes()
                    ultima_limpeza = time.time()  

                print("\nAguardando novos processos...\n")
            
            except Exception as e_conectar:
                logs.error(f"Erro ao conectar na URL '{url_base}': {str(e_conectar)}")
                time.sleep(2)  # Espera 2 segundos antes de tentar novamente

            finally:
                if driver:
                    encerrar_driver_com_timeout(driver) 
                if profile_dir:
                    shutil.rmtree(profile_dir, ignore_errors=True)
      
            time.sleep(0.1)
          
    except Exception as e_crawler:
        logs.error(f"Erro fatal no crawler: {str(e_crawler)}")

     
def processar_pagina(driver, urlBase, filtrosBase, id_pagina, ids_usuarios, listaElementos, plataforma, total_processados, 
                     quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp):
    try:
        lista_planilha = []
        controles_iniciais(driver)

        pagination_info = driver.find_elements(By.CLASS_NAME, "pagination-information")
        if not pagination_info:
            print("Nenhum elemento de paginação encontrado.\n")
            return

        match = re.search(r'(\d+)(?=\s*itens)', pagination_info[0].text.strip())
        if not match:
            return
    
        total_itens = total_itens_tmp if total_itens_tmp > 0 else int(match.group(1))
        registros = int(filtrosBase["banco"].get("qtd_registros", 0) or 0)

        if  total_itens == registros:
            print(f"Execução interrormpida pelo processo de Heurística - {registros}/{total_itens}\n")
            return  # Interrormpe o processo se a heurística for atendida
        
        retorno_elemento = driver.find_elements(By.CLASS_NAME, value='br-list')
        listaElementos.append(retorno_elemento[:])
        
        if not listaElementos or not listaElementos[-1]:
            return
        
        posicao_index_atual = [1]
        retorno_elemento += listaElementos[-1][posicao_index_atual[-1]].find_elements(By.CLASS_NAME, value='br-item')
        listaElementos.append(retorno_elemento[:])
        
        if len(listaElementos) < 1:
            return

        novalistaElementos = [el.text for el in listaElementos[1][4:] if el.text.strip() != '']
        palavra_chave = list(filtrosBase['banco']['palavraschave'].keys())[0].strip().lower()
        
        quantidade_para_processar, processa_mais_paginas, total_itens_tmp, processar_todos = calcular_quantidade_para_processar(
            total_itens, registros, quantidade_para_processar, processar_dia, hora_atual, palavra_chave
        )
            
        error_timeout = 0
        driver_mapfre, profile_dir_mapfre = None, None
        try:
            driver_mapfre, profile_dir_mapfre = setup_driver_mapfre()
            for texto in islice(novalistaElementos, quantidade_para_processar):
                total_processados += 1
                print(f"PROCESSANDO N°: {total_processados} / TOTAL A SER PROCESSADO: {quantidade_para_processar}")
                
                edital, error_timeout= processar_texto(texto, plataforma, driver, driver_mapfre, urlBase, id_pagina, ids_usuarios, hora_atual, 
                    processar_dia,filtrosBase, lock_editais, editais_em_processamento, error_timeout)
                
                if edital:
                    lista_planilha.append(copy.deepcopy(edital))
        except Exception as e:
            logs.error(f"Erro no processamento de login da mapfre: {e}\n")
        finally:
            if driver_mapfre:
                encerrar_driver_com_timeout(driver_mapfre) 
            if profile_dir_mapfre:
                shutil.rmtree(profile_dir_mapfre, ignore_errors=True)   
                            
        if len(lista_planilha) > 0:
            print(f"Processando Planilhas...\n")
            gerar_excel_registros(lista_planilha, plataforma, True) 
            time.sleep(2)
                
        if processar_todos or processa_mais_paginas:
            processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, filtros, 
                notificacao_config, filtrosBase, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp)
                    
        atualizar_heuristica(id_pagina, total_itens) 
        
    except Exception as e:
        logs.error(f"Erro no processamento da página: {e}\n")


def calcular_quantidade_para_processar(total_itens, registros, quantidade_para_processar, processar_dia, hora_atual, palavra_chave):
    processa_mais_paginas = False
    total_itens_tmp = total_itens
    processar_todos = configuracoes.get(f"processar_todos_{palavra_chave}", False)

    if quantidade_para_processar > 0:
        processa_mais_paginas = True
    elif processar_todos:
        quantidade_para_processar = total_itens
    elif processar_dia and 5 <= hora_atual < 9:
        quantidade_para_processar = 50
    elif total_itens > registros:
        quantidade_para_processar = total_itens - registros
        if quantidade_para_processar > 10:
            processa_mais_paginas = True
    else:
        quantidade_para_processar = 10

    return quantidade_para_processar, processa_mais_paginas, total_itens_tmp, processar_todos

def setup_driver_mapfre():
    driver, profile_dir = criar_driver(mostrar_browser=False)
    url_login = configuracoes.get("mafre", {}).get("url_login")
    driver.get(url_login)
    processar_login_mafre(driver)
    return driver, profile_dir

def processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, 
                                 filtros, notificacao_config, filtrosBase, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp): 
    try:
        print(f"Total Processados {palavra_chave}: {total_processados}/ Total a processar {palavra_chave}: {quantidade_para_processar}\n")
        logs.info(f"Total Processados {palavra_chave}: {total_processados}/ Total a processar {palavra_chave}: {quantidade_para_processar}\n")

        while total_processados < quantidade_para_processar:
            if palavra_chave not in ["obra", "pintura", "reforma"]:
                if 10 < quantidade_para_processar <= 50:
                    tam_pagina = quantidade_para_processar + total_processados
                    pagina = 1
                    if 'tam_pagina=' in urlBase:
                        urlBase = re.sub(r'tam_pagina=\d+', f'tam_pagina={tam_pagina}', urlBase)
                    else:
                        urlBase += f'&tam_pagina={tam_pagina}'

            url = urlBase.replace('&pagina=1', f'&pagina={pagina}')
            print(f"Iniciando processamento da palavra_chave: {palavra_chave} na página: {pagina} url: {url}\n")
            logs.info(f"Iniciando processamento da palavra_chave: {palavra_chave} na página: {pagina} url: {url}\n")

            driver.get(url)
            pagina += 1
            listaElementos = []
            processar_pagina(driver, urlBase, filtrosBase, id_pagina, ids_usuarios, listaElementos, plataforma,  
                            total_processados, quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp)
        
        if palavra_chave in ["obra", "pintura", "reforma"]:
            configuracoes[f"processar_todos_{palavra_chave}"] = False
            atualizar_arquivo_configuracoes()

        carregar_configuracoes()
        filtros["banco"]["qtd_registros"] = retornar_registro_paginas(id_pagina, 4)
        crawler(urlBase, filtros, notificacao_config)
    except Exception as e:
        logs.error(f"Erro no processamento processar_paginas_adicionais: {e}\n")
        
def processar_texto(texto, plataforma, driver, driver_mapfre, urlBase, id_pagina, ids_usuarios, hora_atual, 
                    processar_dia,filtrosBase, lock_editais, editais_em_processamento, error_timeout):
    
    if plataforma == "obra" and not validar_modalidade_obras(texto):
        return None, error_timeout
    
    palavras_destacadas = validar_texto(texto, filtrosBase)
    
    if not palavras_destacadas and plataforma != "obra":
        return None, error_timeout

    hora_antes_extrair_dados = datetime.now().strftime("%H:%M:%S")
    edital = extrair_dados(texto, urlBase)
    link = edital.get("Link", "").strip()

    with lock_editais:
        if link in editais_em_processamento:
            print(f"[IGNORADO - EM PROCESSAMENTO] {link}")
            return None, error_timeout
        editais_em_processamento.add(link)

    try:
        # Filtrar apenas editais do dia se necessário
        if processar_dia and 5 <= hora_atual < 9:
            if datetime.strptime(edital["Data"], "%d/%m/%Y").date() != datetime.today().date():
                return None, error_timeout

        palavras_limpa = [p.strip("'\"") for p in palavras_destacadas if p.strip("'\"")]
        edital["palavras_chave"] = palavras_limpa if palavras_limpa else ""

        edital.update({
            "id_pagina": id_pagina,
            "Descricao": destacar_palavras(limpar_para_mysql(edital['Descricao']), palavras_destacadas),
            "notificar_retorno": True,
            "envio_notificacao": datetime.now()
        })

        # Filtrar apenas editais do dia se necessário
        resultadoExisteEdital = verificar_existencia_edital_new(edital["Link"], edital["Orgao"], edital["Numero"])
        if resultadoExisteEdital:
            print(f"EDITAL JA EXISTE NO BANCO: ", resultadoExisteEdital[0]['link'])
            logs.info(f"Edital já existe no banco: {resultadoExisteEdital[0]['id']} - {resultadoExisteEdital[0]['link']}\n")
            return None, error_timeout
        
        # Processamento por plataforma
        if plataforma == "pncp":
            edital, error_timeout = processar_pncp(edital, driver, driver_mapfre, ids_usuarios, error_timeout, hora_antes_extrair_dados)
        elif plataforma == "obra":
            edital, error_timeout = processar_obra(edital, driver, ids_usuarios, error_timeout)

        return edital, error_timeout
    except Exception as e:
        print(f"[ERRO AO PROCESSAR EDITAL] {link} - {e}")
    finally:
        with lock_editais:
            editais_em_processamento.discard(link)

    return None, error_timeout

def processar_obra(edital, driver, ids_usuarios, error_timeout):
    try:
        novos_dados = extrair_dados_nova_pagina(driver, edital)
        if novos_dados == "TimeoutException":
            return tratar_timeout(edital, error_timeout, ids_usuarios)

        edital.update(novos_dados)
        pasta_killer, pasta_comprimidos = obter_pastas_download(edital, "obra")
        edital["pasta_download"] = pasta_killer
        edital["pasta_comprimidos"] = pasta_comprimidos

        if edital["Uf"].upper() == "RS":
            enviar_mensagem(edital, ids_usuarios, novo_processo=True)
            
        acao_baixar_arquivo(driver, edital, "obra")
        gravar_novo_processo(edital, "obra")
        return edital, 0
    
    except Exception as e:
        print(f"[ERRO no processar_obra:] {edital.get('Link', '').strip()} - {e}")

def processar_pncp(edital, driver, driver_mapfre, ids_usuarios, error_timeout, hora_antes_extrair_dados):
    try:
        novos_dados = extrair_dados_nova_pagina_para_mapfre(driver, edital)
        edital.update(novos_dados)

        retorno, msg, ramos_valores = validar_criar_reserva(edital)
        if retorno:
            edital["ramos_valores"] = ramos_valores
        else:
            edital["aviso_reserva"] = msg
            enviar_mensagem(edital, ids_usuarios, novo_processo=True)
            gravar_novo_processo(edital, "pncp")
            return edital, error_timeout

        if novos_dados == "TimeoutException":
            return tratar_timeout(edital, error_timeout, ids_usuarios)

        pasta_killer, pasta_comprimidos = obter_pastas_download(edital, "pncp")
        edital["pasta_download"] = pasta_killer
        edital["pasta_comprimidos"] = pasta_comprimidos

        thread_download = threading.Thread(target=baixar_em_thread, args=(driver, edital, "pncp"))
        thread_download.start()
        hora_antes_iniciar_reserva = datetime.now().strftime("%H:%M:%S")

        resultado_queue = queue.Queue()
        def chamar_inicializar_pagina():
            with lock_pos_login:
                msg, ids, imgs = processar_pesquisa_licitacao(driver_mapfre, edital, thread_download)
                resultado_queue.put((msg, ids, imgs))

        thread_mapfre = threading.Thread(target=chamar_inicializar_pagina)
        thread_mapfre.start()
        thread_mapfre.join()

        # Tempo gasto
        formato = "%H:%M:%S"
        inicio = datetime.strptime(hora_antes_extrair_dados, formato)
        fim = datetime.strptime(datetime.now().strftime("%H:%M:%S"), formato)
        total_segundos = int((fim - inicio).total_seconds())
        print(f"TEMPO EXTRAIR DADOS ATE APOS REGISTRO MAPFRE: {total_segundos}")
        edital["horario_termino"] = str(timedelta(seconds=int((fim - inicio).total_seconds())))

        if not resultado_queue.empty():
            msg, ids, imgs = resultado_queue.get()
            tratar_resultado_mafre(msg, ids, imgs, edital, hora_antes_iniciar_reserva)

        novos_dados = extrair_dados_nova_pagina(driver, edital)
        edital.update(novos_dados)
        enviar_mensagem(edital, ids_usuarios, novo_processo=True)
        gravar_novo_processo(edital, "pncp")
        return edital, 0
    
    except Exception as e:
        print(f"[ERRO no processar_pncp:] {edital.get('Link', '').strip()} - {e}")

def tratar_resultado_mafre(msg, ids, imgs, edital, hora_antes_iniciar_reserva):
    try:
        blocos = re.split(r";\s*", msg)
        for parte in blocos:
            parte_lower = parte.lower()
            if "reserva já cadastrada" in parte_lower:
                tratar_reserva_existente(parte, ids, imgs, edital)
            elif "sucesso" in parte_lower:
                tratar_reserva_sucesso(parte, ids, edital, hora_antes_iniciar_reserva)
            elif "erro" in parte_lower:
                edital["aviso_reserva"] = parte
    except Exception as e:
        print(f"[ERRO no tratar_resultado_mafre:] {edital.get('Link', '').strip()} - {e}")
        
def tratar_reserva_existente(parte, ids, imgs, edital):
    try:
        reservas_encontradas = re.findall(r"reserva:\s*(\d+)", parte)
        ramos_encontrados = re.findall(r"ramo:\s*(\d+)", parte)

        for i, id_val in enumerate(ids, start=1):
            edital[f"reserva_perdida_{i}"] = id_val
            match_id_url = re.search(r"id=(\d+)", id_val)
            if not match_id_url:
                continue

            id_extraido = match_id_url.group(1)
            id_reserva = reservas_encontradas[i - 1] if i - 1 < len(reservas_encontradas) else None
            ramo_id = ramos_encontrados[i - 1] if i - 1 < len(ramos_encontrados) else None

            if id_reserva == id_extraido and ramo_id:
                edital[f"ramo_perdido_{i}"] = NOMES_RAMO.get(ramo_id, f"Ramo {ramo_id}")
            if imgs and i - 1 < len(imgs):
                edital[f"img_{i}"] = imgs[i - 1]
    except Exception as e:
        print(f"[ERRO no tratar_reserva_existente:] {edital.get('Link', '').strip()} - {e}")

def tratar_reserva_sucesso(parte, ids, edital, hora_antes_iniciar_reserva):
    try: 
        reservas_encontradas = re.findall(r"reserva:\s*(\d+)", parte)
        ramos_encontrados = re.findall(r"ramo:\s*(\d+)", parte)

        formato = "%H:%M:%S"

        for i, id_val in enumerate(ids, start=1):
            edital[f"link_reserva_{i}"] = id_val
            match_id_url = re.search(r"id=(\d+)", id_val)
            if not match_id_url:
                continue

            id_extraido = match_id_url.group(1)
            id_reserva = reservas_encontradas[i - 1] if i - 1 < len(reservas_encontradas) else None
            ramo_id = ramos_encontrados[i - 1] if i - 1 < len(ramos_encontrados) else None

            if ramo_id:
                edital[f"ramo_{i}"] = NOMES_RAMO.get(ramo_id, f"Ramo {ramo_id}")

            if id_reserva == id_extraido and "data inclusao" in parte.lower():
                match = re.search(r'data inclusao:\s*\d{2}/\d{2}/\d{4}\s+(\d{2}:\d{2}:\d{2})', parte.lower())
                if match:
                    edital[f"horario_arq_anexado_{i}"] = match.group(1)
                    hora_anexo = match.group(1)

                    hora_inicio = datetime.strptime(hora_antes_iniciar_reserva, formato)
                    hora_termino = datetime.strptime(hora_anexo, formato)
                    total_segundos = int((hora_termino - hora_inicio).total_seconds())

                    edital[f"diferença_inicio_anexo_{i}"] = str(timedelta(seconds=total_segundos))
                    
    except Exception as e:
        print(f"[ERRO no tratar_reserva_sucesso:] {edital.get('Link', '').strip()} - {e}")
  
def tratar_timeout(edital, error_timeout, ids_usuarios):
    """Gerencia erros de timeout e decide se continua ou pausa processamento."""
    error_timeout += 1
    if error_timeout >= 3:
        print("\n" + "="*94)
        print("ERRO NO SITE: MAIS DE 3 TIMEOUTS. AGUARDANDO 5 MINUTOS PARA TENTAR NOVAMENTE.")
        print("\n" + "="*94 + "\n")
        enviar_mensagem(edital, ids_usuarios, novo_processo=True, erro=True)
        time.sleep(300)
        return None, 0  # zera contagem após pausa
    return None, error_timeout
        
                
def baixar_em_thread(driver, edital, plataforma):
    try:
        acao_baixar_arquivo(driver, edital, plataforma)
    except Exception as e:
        logs.warning(f"Download paralelo falhou: {e}")

def obter_pastas_download(edital, plataforma):
    try:
        pasta_edital, _ , pasta_comprimidos = obter_caminho_edital(edital, plataforma)
        edital["pasta_edital_original"] = pasta_edital 
        raiz_local = configuracoes.get("raiz_local")
        raiz_server = configuracoes.get("raiz_server")
        pasta_killer = pasta_edital.replace(raiz_local, raiz_server)
        pasta_killer_comprimidos = pasta_comprimidos.replace(raiz_local, raiz_server)
        pasta_killer = os.path.normpath(pasta_killer)
        pasta_killer_comprimidos = os.path.normpath(pasta_killer_comprimidos)
        
        return pasta_killer, pasta_killer_comprimidos
    except Exception as e:
        return None 

def validar_modalidade_obras (texto):
    modalidade = extrair_texto(texto, 'Modalidade da Contratação: ')
    if modalidade not in ("Concorrência - Eletrônica", "Concorrência - Presencial", "Pregão - Eletrônico",
                            "Pregão - Presencial", "Dispensa", "Dispensa - Eletrônica"):
        return False
    else:
        return True

def validar_texto(texto, filtrosBase):
    pos_objeto = texto.lower().find("objeto:")
    if pos_objeto == -1:
        return [] 

    texto_objeto = texto[pos_objeto + len("Objeto:"):].strip()
    texto_normalizado = unidecode(texto_objeto.lower())

    palavras_encontradas = []

    for palavra_chave, palavras_bloqueadas in filtrosBase['banco']['palavraschave'].items():
        if palavra_chave not in texto_normalizado:
            continue

        # Bloqueia se encontrar uma palavra proibida
        if any(re.search(rf'\b{re.escape(pb)}\b', texto_normalizado) for pb in palavras_bloqueadas):
            continue

        # Busca todas as palavras do texto original que começam com a palavra-chave
        palavras = texto_objeto.split()
        palavras_encontradas.extend([w.strip(string.punctuation) for w in palavras if unidecode(w.lower()).startswith(palavra_chave)])

    return palavras_encontradas

def destacar_palavras(texto, palavras):

    #Destaca todas as ocorrências exatas das palavras no texto com <b></b>, sem sobreposição e respeitando posições.
    if not palavras:
        return texto

    # Ordenar por tamanho decrescente para evitar conflitos em palavras contidas umas nas outras
    palavras_ordenadas = sorted(set(palavras), key=len, reverse=True)
    
    # Regex para destacar cada palavra, usando boundaries para evitar partes de outras palavras
    def substituir(match):
        return f"<b>{match.group(0)}</b>"

    for palavra in palavras_ordenadas:
        # Apenas destaca se for uma palavra completa (pode ajustar \b conforme o caso)
        texto = re.sub(rf'\b{re.escape(palavra)}\b', substituir, texto, flags=re.IGNORECASE)

    return texto


def extrair_dados(texto, urlBase):
    id_aux = extrair_texto(texto, 'Id contratação PNCP: ')
    numero = extrair_numero_edital(texto)
    
    # Só mantém se tiver barra (/) no número extraído
    numero2 = numero.split('/')[0] if numero and '/' in numero else numero
    
    return {
        'Numero':numero,
        'NumeroAux': numero2,
        'IdContratacaoPncp': id_aux,
        'Licitacao': extrair_texto(texto, 'Modalidade da Contratação: '),
        'Data': extrair_texto(texto, 'Última Atualização: '),
        'Orgao': extrair_texto(texto, 'Órgão: '),
        'Municipio': extrair_texto(texto, 'Local: '),
        'Uf': extrair_texto(texto, 'Local: ').split('/')[1],
        'Descricao': extrair_texto(texto, 'Objeto: '),
        'Cnpj': id_aux.split('-')[0],
        'Link': f"{urlBase.split('?')[0]}/{id_aux.split('-')[0]}/{id_aux.split('/')[-1]}/{id_aux.split('-')[2].split('/')[0].lstrip('0')}"
    }
    
def extrair_numero_edital(texto):
    
    texto = texto.split('\n', 1)[0]
    # Remove conteúdos entre parênteses e pipes
    texto = re.sub(r'\([^)]*\)', '', texto)
    texto = texto.replace('|', ' ')
    texto = texto.replace(' /', '/')  # Remove espaços antes da barra final
 
    # Remove tudo após "nº" até o primeiro número
    texto = re.sub(r'(n[ºo])\s*[^\d/]*', r'\1 ', texto, flags=re.IGNORECASE)
    
    # Remove espaços após "nº" ou "n°"
    texto = re.sub(r'(n[ºo]\s+[A-Z]{2})\s+', r'\1', texto)

    # Tenta encontrar a parte após "nº" com números/letras/separadores
    match = re.search(
        r'n[ºo]\s*([A-Za-z0-9\-./]+)', 
        texto, 
        re.IGNORECASE
    )

    if match:
        numero = match.group(1).strip()

        # Remove prefixos com letras (ex: PE, PD, PMJ, PL)
        numero = re.sub(r'^[A-Za-z\-]+', '', numero)

        # Remove prefixos numéricos com hífen (ex: 2025-561 → 561)
        numero = re.sub(r'^\d{4}-', '', numero)
        
        # Remove letras no meio de partes separadas por /
        numero = re.sub(r'/[A-Za-z]+(?=/)', '', numero)

        # Remove partes como -PRORROGAÇÃO/2025 ou -DIV/2025
        numero = re.sub(r'-[A-Za-z]+(?=/)', '', numero)

        # Remove hífens intermediários com número (ex: 561-1/2025 → 561/2025)
        numero = re.sub(r'-(\d+)(?=/)', '', numero)

        # Remove letras no final antes da barra (ex: 2325PE/2025 → 2325/2025)
        numero = re.sub(r'([0-9])([A-Za-z]+)(?=/)', r'\1', numero)

        return numero.strip()

    return None
  
def extrair_texto(texto, chave):
    """Extrai o valor associado a uma chave no texto."""
    try:
        return texto.split(chave)[1].split('\n')[0].strip().replace("'", "")
    except IndexError:
        return None

def extrair_dados_nova_pagina_para_mapfre(driver, edital):
    tentativas = 2 
    for tentativa in range(tentativas):
        try:
            url_link = edital.get("Link", "")
            driver.get(url_link)
            elementos_nova_pagina = WebDriverWait(driver, 40).until(
                EC.presence_of_all_elements_located((By.XPATH, '//div[@id="main-content"]/pncp-item-detail/div'))
            )
            texto = elementos_nova_pagina[0].text
            data_fim_recebimento_str = extrair_data_com_horario(texto, 'Data fim de recebimento de propostas: ') or None
            data_fim = None
            hora_fim = None
            match = re.search(r'de\s+(\d+)\s+itens', texto)
            numero_itens = match.group(1) if match else '0'
                    
            if data_fim_recebimento_str:
                partes = data_fim_recebimento_str.split(" ")
                if len(partes) == 2:
                    data_fim, hora_fim = partes
                    
            novos_campos = {
                'DataFimRecebimentoProposta': data_fim_recebimento_str,
                "DataFim": data_fim,
                "HoraFim": hora_fim,
            }       
            
            # Caso o numero de itens no texto inicial não é econtrado tenta em outro parte do html
            if numero_itens == '0':
                elemento_itens = elementos_nova_pagina[0].find_element(By.CLASS_NAME, 'pagination-information')
                texto = elemento_itens.text
                match = re.search(r'de\s+(\d+)\s+itens', texto)
                numero_itens = match.group(1) if match else '0'
                novos_campos['QuantidadeItens'] = numero_itens
            else:
                novos_campos['QuantidadeItens'] = numero_itens          
                         
            #pega o VALOR ESTIMADO, se vir RS 0,00 coloca SEM ESTIMADO
            elemento_valor_total = elementos_nova_pagina[0].find_elements(By.XPATH, './/div[8]') 
            if elemento_valor_total:
                texto = elemento_valor_total[0].text
                valor_total_estimado =  extrair_texto(texto, 'VALOR TOTAL ESTIMADO DA COMPRA\n') or None
                if valor_total_estimado:
                    if valor_total_estimado.strip() not in ['0,00', '0.00', '0', 'R$ 0,00']:
                        novos_campos['ValorTotalEstimadoCompra'] = valor_total_estimado
                    else:
                        novos_campos['ValorTotalEstimadoCompra'] = 'SEM ESTIMADO'
                else:
                    elemento_valor_total_2 = elementos_nova_pagina[0].find_elements(By.XPATH, './/div[9]')
                    texto = elemento_valor_total_2[0].text
                    valor_total_estimado = extrair_texto(texto, 'VALOR TOTAL ESTIMADO DA COMPRA\n') or None
                    if valor_total_estimado and valor_total_estimado.strip() not in ['0,00', '0.00', '0', 'R$ 0,00']:
                        novos_campos['ValorTotalEstimadoCompra'] = valor_total_estimado
                    else:
                        novos_campos['ValorTotalEstimadoCompra'] = 'SEM ESTIMADO'
            
            
            return novos_campos 
        except Exception as e:
            if tentativa < tentativas - 1:
                    print(f"Erro na tentativa extrair_dados_nova_pagina_para_mapfre {tentativa + 1}: Tentando novamente...\n")
                    time.sleep(0.5)  
            else:
                print(f"Erro final em extrair_dados_nova_pagina_para_mapfre: {type(e).__name__}: edital link:",  edital["Link"] ,"\n")
                logs.error(f"Erro final em extrair_dados_nova_pagina_para_mapfre: {type(e).__name__}: edital link:",  edital["Link"] ,"\n")
                string_error = type(e).__name__
                return string_error
    
    return []

def extrair_dados_nova_pagina(driver, edital):
    tentativas = 2 
    for tentativa in range(tentativas):               
        try: 
            url_link = edital.get("Link", "")
            driver.get(url_link)
            elementos_nova_pagina = WebDriverWait(driver, 40).until(
                EC.presence_of_all_elements_located((By.XPATH, '//div[@id="main-content"]/pncp-item-detail/div'))
            )
            texto = elementos_nova_pagina[0].text
              
            novos_campos = {
                'DataInicioRecebimentoProposta': extrair_data_com_horario(texto, 'Data de início de recebimento de propostas: ') or None,
                'CodigoUnidadeCompradora': extrair_codigo_unidade_compradora(texto),
                'ModoDeDisputa': extrair_texto(texto, 'Modo de disputa: '),
                'Situacao':extrair_texto(texto, 'Situação: '),
            }
   
            button = "Acessar Contratação" in texto
        
            # tenta abrir o link do botão em nova aba e capturar a URL
            link = None
            if button:
                try:
                    botao = elementos_nova_pagina[0].find_element(By.XPATH, './/div[1]/div[2]/div/button')
                    
                    janela_antes = driver.window_handles
                    botao.click()

                    WebDriverWait(driver, 30).until(lambda d: len(d.window_handles) > len(janela_antes))
                    nova_janela = [w for w in driver.window_handles if w not in janela_antes][0]
                    driver.switch_to.window(nova_janela)

                    link = driver.current_url

                    driver.close()
                    driver.switch_to.window(janela_antes[-1])

                except NoSuchElementException:
                    pass
                except TimeoutException:
                    print("Timeout esperando mudança após clique no botão\n")
                except Exception as e:
                    print("Erro ao tentar abrir link do botão:", e)

            if link:
                novos_campos['LinkBotao'] = link
                
            return novos_campos 
        
        except Exception as e:
            if tentativa < tentativas - 1:
                print(f"Erro na tentativa extrair_dados_nova_pagina {tentativa + 1}: Tentando novamente...\n")
                time.sleep(0.5)  
            else:
                print(f"Erro final em extrair_dados_nova_pagina: {type(e).__name__}: edital link:",  edital["Link"] ,"\n")
                logs.error(f"Erro final em extrair_dados_nova_pagina: {type(e).__name__}: edital link:",  edital["Link"] ,"\n")
                string_error = type(e).__name__
                return string_error
    return []
        
                        
def extrair_data_com_horario(texto, chave):
    """Extrai a data e horário, removendo apenas '(horário de Brasília)'."""
    valor = extrair_texto(texto, chave)
    if valor:
        return re.sub(r'\s*\(horário de Brasília\)', '', valor)  # Remove apenas essa parte
    return None

def extrair_codigo_unidade_compradora(texto):
    """Extrai apenas o código antes do hífen da unidade compradora."""
    valor = extrair_texto(texto, 'Unidade compradora: ')
    if valor:
        return valor.split(' - ')[0]  # Pega apenas o código antes do hífen
    return None
                      
def acao_baixar_arquivo(driver, edital, plataforma):
    tentativas = 3
    arquivos_baixados = False;
    for tentativa in range(tentativas):
        try:
            #driver.execute_script("window.open(arguments[0], '_blank');", edital["Link"])
            #time.sleep(0.2)
            #driver.switch_to.window(driver.window_handles[-1])
            # Espera até que o elemento pai esteja presente
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="main-content"]/pncp-item-detail/div/pncp-tab-set/div/pncp-tab[2]/div/div/pncp-table/div/ngx-datatable/div/datatable-body/datatable-selection/datatable-scroller'))
            )
            time.sleep(0.2)
            # Espera até que pelo menos um row apareça
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "datatable-row-wrapper"))
            )
            time.sleep(0.2)
            elemento = driver.find_element(By.XPATH, '//*[@id="main-content"]/pncp-item-detail/div/pncp-tab-set/div/pncp-tab[2]/div/div/pncp-table/div/ngx-datatable/div/datatable-body/datatable-selection/datatable-scroller')
            rows = elemento.find_elements(By.CSS_SELECTOR, "datatable-row-wrapper")
            arquivos =[]
            for row in rows:
                try:
                    nome = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(1) span").get_attribute("innerText").strip()
                except:
                    nome = ""

                try:
                    data = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(2) div").get_attribute("innerText").strip()
                except:
                    data = ""

                try:
                    tipo = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(3) span").get_attribute("innerText").strip()
                except:
                    tipo = ""

                try:
                    link = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(4) a").get_attribute("href")
                except:
                    link = ""
                    
                arquivos.append({
                    "nome": nome,
                    "data": data,
                    "tipo": tipo,
                    "link": link
                })
                
            arquivos_baixados = salvar_arquivos(arquivos, edital, plataforma)
            
        except Exception as e:
            if tentativa < tentativas - 1:
                print(f"Erro na tentativa acao_baixar_arquivo {tentativa + 1}: Tentando novamente...\n")
                time.sleep(2)  
            else:
                print(f"Erro final em acao_baixar_arquivo:edital link:",  edital["Link"] ,"\n")
                logs.error(f"Erro final em acao_baixar_arquivo:{str(e)} edital link:",  edital["Link"] ,"\n")
                return False 
            
        #finally:
            #driver.close()
            #driver.switch_to.window(driver.window_handles[0])  
    
        if tentativa >= 1:
            return arquivos_baixados
    return False
           
             
def salvar_arquivos(arquivos, edital, plataforma):
    arquivos_baixados = 0
    compactado = False
    try:
        pasta_edital, pasta_dia, pasta_compridos = obter_caminho_edital(edital, plataforma)

        # Criar apenas a pasta do dia se a base já existir
        if not os.path.exists(pasta_dia):
            os.makedirs(pasta_dia)  # Criar toda a estrutura
            print(f"Criado diretório base: {pasta_dia}\n")
        if not os.path.exists(pasta_edital):
            os.makedirs(pasta_edital)  # Criar apenas a pasta do dia
            print(f"Criado diretório para data {pasta_edital}\n")
            
        quantidadeTipoEdital = sum(1 for arquivo in arquivos if arquivo.get("tipo").lower() == "edital")
      
        for arquivo in arquivos:
            tipo = arquivo.get("tipo")
            nome_bruto = str(arquivo.get("nome", "Desconhecido")).strip()
            nome_limpo = re.sub(r'[\\/:*?"<>|]', '_', nome_bruto)
        
            max_tentativas = 2
            for tentativa in range(1, max_tentativas + 1):
                link = arquivo.get("link", "").strip()
                if not link:
                    print(f"Link de download vazio, ignorando arquivo. Edital link - ", edital["Link"])
                    logs.error(f"Link de download vazio, ignorando arquivo. Edital link - ", edital["Link"])
                    continue  # se estiver em um loop, ou return/break conforme necessário
    
                response = requests.get(arquivo["link"], stream=True)
                if response.status_code == 200:
                    # Usa o nome original ou gera com base no tipo
                    base_nome, ext = obter_extensao_response(response, nome_limpo)
                    
                    if not base_nome:
                        base_nome = nome_limpo.replace('.', '-')
                    else:
                        base_nome = base_nome.replace('.', '-')
                        
                    if "edital" in tipo.lower():
                        if quantidadeTipoEdital > 1:
                            nome_arquivo = f"1-{base_nome}{ext}"
                        else:
                            nome_arquivo = f"1-Edital{ext}"
                    else:
                        nome_arquivo = f"{base_nome}{ext}"

                    caminho_completo = os.path.join(pasta_edital, nome_arquivo)
                    caminho_em_compactados = os.path.join(pasta_edital, 'compactados', nome_arquivo)
                    
                    if os.path.exists(caminho_completo) or os.path.exists(caminho_em_compactados):
                        if os.path.exists(caminho_completo):
                            print(f"O arquivo {nome_arquivo} já existe no caminho {caminho_completo}.\n")
                        if os.path.exists(caminho_em_compactados):
                             print(f"O arquivo {nome_arquivo} já existe no caminho {caminho_em_compactados}.\n")  
                        break
                    else:
                        with open(caminho_completo, "wb") as file:
                            shutil.copyfileobj(response.raw, file)
                        arquivos_baixados += 1
                        print(f"Arquivo salvo: {caminho_completo}\n")
                        logs.info(f"Arquivo salvo: {caminho_completo}\n")
                        
                        executar_verificacao_arquivos(caminho_completo, ext, pasta_edital, nome_arquivo)
                        break
                
                else:
                    print(f"Tentativa {tentativa} falhou ao baixar: {arquivo['link']}\n")
                    logs.error(f"Tentativa {tentativa} falhou ao baixar: {arquivo['link']}\n")
                    if tentativa == max_tentativas:
                        print(f"Erro final ao baixar {arquivo['link']}\n")
                        logs.error(f"Erro final ao baixar arquivo: {arquivo['link']}\n")
                                     
        # Tentar compactar apenas se algum arquivo foi baixado
        if arquivos_baixados > 0:
            compactado = compactar_arquivos(pasta_edital, pasta_compridos)
        
        return arquivos_baixados > 0, compactado
                        
    except Exception as e:
        logs.error("Erro ao salvar arquivos - ", str(e))

def compactar_arquivos(pasta_edital, pasta_compridos):
    try:
        nome_pasta = os.path.basename(pasta_edital)
        zip_path = os.path.join(pasta_compridos, f"{nome_pasta}.zip")

        # Cria o destino, se não existir
        if not os.path.exists(pasta_compridos):
            os.makedirs(pasta_compridos)

        if os.path.exists(zip_path):
            print(f"O arquivo {nome_pasta}.zip já existe no caminho {zip_path}.")
            return
            
        # Remove a pasta "compactados" de dentro da origem, se existir
        #caminho_compactados = os.path.join(pasta_edital, 'compactados')
        #if os.path.exists(caminho_compactados):
            #shutil.rmtree(caminho_compactados)

        # Conta os arquivos, ignorando a pasta "compactados"
        total_arquivos = 0
        for raiz, _, arquivos in os.walk(pasta_edital):
            if 'compactados' in raiz:
                continue
            total_arquivos += len(arquivos)

        if total_arquivos <= 1:
            print(f"Não há mais de 1 arquivo em '{pasta_edital}', não será compactado.")
            return True
        
        # Cria o arquivo ZIP
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for raiz, _, arquivos in os.walk(pasta_edital):
                if 'compactados' in raiz:
                    continue
                for arquivo in arquivos:
                    caminho_completo = os.path.join(raiz, arquivo)
                    caminho_relativo = os.path.relpath(caminho_completo, pasta_edital)
                    zipf.write(caminho_completo, arcname=caminho_relativo)

        print(f"Pasta '{pasta_edital}' compactada como '{zip_path}'.")
        logs.info(f"Pasta '{pasta_edital}' compactada como '{zip_path}'")
        return True
                
    except Exception as e:
        logs.error(f"Erro ao compactar arquivos, error: {str(e)}")
        return False

def obter_extensao_response(response, nome_limpo):
    try:
        # Lista de extensões conhecidas
        extensoes_validas = configuracoes.get("extensoes_validas")
        
        # 1.Verifica se nome do arquivo ja termina com extensão válida
        tem_extensao_valida = any(nome_limpo.lower().endswith(ext) for ext in extensoes_validas)
        if tem_extensao_valida:
            base, ext = os.path.splitext(nome_limpo)
            return base, ext.lower()
        
        # 2. Verifica se vem no Content-Disposition
        cd = response.headers.get("Content-Disposition")
        if cd:
            match = re.findall('filename="?([^"]+)"?', cd)
            if match:
                _, ext = os.path.splitext(match[0])
                if ext:
                    return None, ext.lower()

        # 3. Tenta adivinhar via mimetype
        content_type = response.headers.get("Content-Type")
        if content_type:
            ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if ext:
                return None, ext.lower()

        # 4. Usa .pdf como fallback
        return None, ".pdf"
    
    except Exception as e:
        logs.error("Erro ao obter_extensao_response arquivos - ", str(e))
        return None, ".pdf"

def obter_caminho_edital(edital, plataforma):
    locale.setlocale(locale.LC_TIME, "Portuguese_Brazil.1252")
    
    # Obter datas
    dia = datetime.today().strftime("%Y-%m-%d")
    dia_obra = datetime.today().strftime("%m.%d")
    ano_atual = datetime.today().strftime("%Y")
    mes_atual = datetime.today().strftime("%B").capitalize()
    mes_atual = mes_atual.upper()
    
    # Limpar caracteres inválidos do número do edital e nome do órgão
    numero_edital = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Numero", "Desconhecido")).strip())
    orgao_edital = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Orgao", "Desconhecido")).strip())
    estado = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Uf", "Desconhecido")).strip())
    
    data_raw = str(edital.get("DataFim", dia_obra)).strip()
    data_sem_ano = re.sub(r'/\d{4}$', '', data_raw)
    data_obra = re.sub(r'[\\/:*?"<>|]', '.', data_sem_ano)
    
    pasta_downloads = configuracoes.get('pasta_downloads')
    
    # Caminho das pastas
    pasta_dia = os.path.join(pasta_downloads, f"{ano_atual}/{mes_atual}/{dia}")
    pasta_edital =""
    
    if plataforma == 'obra':
        pasta_edital = os.path.join(pasta_dia, f"{data_obra} - {estado} - {orgao_edital}")      
    else:
        pasta_edital = os.path.join(pasta_dia, f"{numero_edital}-{orgao_edital}")
       
        
    pasta_comprimidos = os.path.join(pasta_dia,"Arquivos Comprimidos")
    
    return pasta_edital, pasta_dia, pasta_comprimidos

def comprimir_pdf(caminho_pdf):
    try:
        novo_pdf = f"{os.path.splitext(caminho_pdf)[0]}_comprimido.pdf"
        args = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={novo_pdf}",
            caminho_pdf
        ]
        ghostscript.Ghostscript(*args)
        print(f"PDF {caminho_pdf} comprimido e salvo como {novo_pdf}")
        logs.info(f"PDF comprimido: {caminho_pdf}")
        return novo_pdf      
    except Exception as e:  
        print(f"Erro ao comprimir {caminho_pdf} com Ghostscript: {e}")
        logs.error(f"Erro ao comprimir {caminho_pdf}: {str(e)}")
        return caminho_pdf


def mover_campactados(caminho_compactado, pasta_edital,nome_arquivo):
    # Mover o ZIP ou RAR original para a pasta 'compactados'   
    pasta_compactados = os.path.join(pasta_edital, 'compactados')
    if not os.path.exists(pasta_compactados):
        os.makedirs(pasta_compactados, exist_ok=True)   
    destino = os.path.join(pasta_compactados, nome_arquivo)
    shutil.move(caminho_compactado, destino)
    print(f"Arquivo compactado movido para: {destino}")
    logs.info(f"Arquivo compactado movido para: {destino}")

def mover_arquivos(caminho, pasta_edital):
     # Verifica se é um diretório
    if os.path.isdir(caminho):
        # Move todos os arquivos de dentro do diretório para a pasta raiz
        for raiz, _, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                origem = os.path.join(raiz, arquivo)
                destino = os.path.join(pasta_edital, arquivo)
                shutil.move(origem, destino)  # Move o arquivo para a raiz

        # Após mover, remove o diretório original vazio
        shutil.rmtree(caminho)
              
def processar_arquivos_compactados(caminho_compactado, pasta_edital, nome_arquivo, ext):
    try:
        if ext == '.zip':
            with zipfile.ZipFile(caminho_compactado, 'r') as zip_ref:
                zip_ref.extractall(pasta_edital)
                print(f"ZIP extraído para: {pasta_edital}")
                logs.info(f"ZIP extraído: {caminho_compactado}")
        elif ext == '.rar':
            try:
                unrar_path = configuracoes.get("UNRAR_TOOL")
                rarfile.UNRAR_TOOL = unrar_path
                with rarfile.RarFile(caminho_compactado, 'r') as rar_ref:
                        rar_ref.extractall(pasta_edital)
                        print(f"RAR extraído para: {pasta_edital}")
                        logs.info(f"RAR extraído: {caminho_compactado}")
            except rarfile.RarCannotExec as e:
                print("Erro: 'unrar.exe' não encontrado.")
                logs.error(f"Erro ao extrair RAR: {e}")
                return
        else:
            print("Formato não suportado.")
            logs.warning(f"Formato não suportado: {caminho_compactado}")
            return

        mover_campactados(caminho_compactado, pasta_edital, nome_arquivo)

         # Primeira iteração: mover os diretórios
        for item in list(os.listdir(pasta_edital)):
            caminho_item = os.path.join(pasta_edital, item)
            if os.path.isdir(caminho_item) and item != 'compactados':
                mover_arquivos(caminho_item, pasta_edital)

        # Segunda iteração: processar os arquivos agora que tudo está na raiz
        for item in os.listdir(pasta_edital):
            caminho_item = os.path.join(pasta_edital, item)
            ext = os.path.splitext(item)[1].lower()
            if item == 'compactados':
                continue
            executar_verificacao_arquivos(caminho_item, ext, pasta_edital, item)
            
    except zipfile.BadZipFile:
        print(f"Erro: {nome_arquivo} não é um ZIP válido.")
        logs.error(f"Erro ao extrair ZIP: {caminho_compactado}")
    except rarfile.Error as e:
        print(f"Erro ao extrair RAR: {e}")
        logs.error(f"Erro ao extrair RAR: {caminho_compactado}")
          
def executar_verificacao_arquivos(caminho_completo, ext, pasta_edital, nome_arquivo):
    try:
        extensoes_imgs = configuracoes.get("extensoes_imgs", [])
        extensoes_panilhas = configuracoes.get("extensoes_planilhas", [])
        formatos_para_docx = configuracoes.get("formatos_para_docx", [])
        if ext.lower() == ".zip" or ext.lower() == ".rar" :
            processar_arquivos_compactados(caminho_completo, pasta_edital, nome_arquivo, ext)
        elif ext.lower() == ".pdf":
            verificacao_comprimir_arquivo(caminho_completo)         
        elif ext.lower() in formatos_para_docx:
            converter_para_docx(caminho_completo)   
        elif ext.lower() in extensoes_imgs:
            converter_para_pdf(nome_arquivo, pasta_edital)
        elif ext.lower() in extensoes_panilhas:
            converter_para_xlsx(caminho_completo)
            
    except Exception as e:
        logs.error("Erro ao executar_verificacao_arquivos - ", str(e))


def converter_para_xlsx(arquivo_origem):
    nome_arquivo_sem_extensao, ext = os.path.splitext(arquivo_origem)
    novo_arquivo_xlsx = f"{nome_arquivo_sem_extensao}.xlsx"

    if ext == '.csv':
        try:
            df = pd.read_csv(arquivo_origem)
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Convertido para .xlsx: {arquivo_origem}")
            logs.info(f"Convertido para .xlsx: {arquivo_origem}")
        except pd.errors.EmptyDataError:
            df = pd.DataFrame()
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Arquivo está vazio, mas foi convertido para .xlsx:{arquivo_origem}")
            logs.info(f"Arquivo está vazio, mas foi convertido para .xlsx:{arquivo_origem}")
        except Exception as e:
            print(f"Erro ao converter {arquivo_origem}: {e}")
    elif ext in ['.xlsm', '.ods']:
        try:
            df = pd.read_excel(arquivo_origem, engine='odf' if ext == '.ods' else None)
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Convertido para .xlsx:  {arquivo_origem}")
            logs.info(f"Convertido para .xlsx:  {arquivo_origem}")
        except Exception as e:
            df = pd.DataFrame()
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Arquivo está vazio ou ocorreu um erro, mas foi convertido para .xlsx:  {arquivo_origem} - error: {e}")
            logs.info(f"Arquivo está vazio ou ocorreu um erro, mas foi convertido para .xlsx:  {arquivo_origem} - error: {e}")
            
def converter_para_pdf(imagem, pasta_edital):
        try:
            img = Image.open(imagem).convert('RGB')
            nome_arquivo_sem_extensao = os.path.splitext(os.path.basename(imagem))[0]
            nome_arquivo_saida = os.path.join(pasta_edital, f"{nome_arquivo_sem_extensao}.pdf")
            img.save(nome_arquivo_saida)
            print(f"Convertido {imagem} para PDF em {nome_arquivo_saida}")
            logs.info(f"Convertido {imagem} para PDF em {nome_arquivo_saida}")
        except Exception as e:
            print(f"Erro ao converter {imagem} para PDF: {e}")
            logs.error(f"Erro ao converter {imagem} para PDF: {e}")


def verificacao_comprimir_arquivo(caminho_completo):
    limite_kb = configuracoes.get("limite_kb")
    tamanho_arquivo = os.path.getsize(caminho_completo)
    if tamanho_arquivo / 1024 > limite_kb:
        comprimido = comprimir_pdf(caminho_completo)
        tamanho_novo = os.path.getsize(comprimido)

        if tamanho_novo / 1024 > limite_kb:
            dividir_pdf_em_partes(comprimido, limite_kb)
            
def dividir_pdf_em_partes(caminho_pdf, limite_kb):
    try:
        reader = PdfReader(caminho_pdf)
        total_paginas = len(reader.pages)
        tamanho_total_kb = os.path.getsize(caminho_pdf) / 1024

        partes_necessarias = math.ceil(tamanho_total_kb / limite_kb)
        paginas_por_parte = total_paginas // partes_necessarias
        
        for i in range(partes_necessarias):
            writer = PdfWriter()
            
            inicio = i * paginas_por_parte
            fim = (i + 1) * paginas_por_parte if i < partes_necessarias - 1 else total_paginas

            for j in range(inicio, fim):
                writer.add_page(reader.pages[j])

            caminho_parte = caminho_pdf.replace('.pdf', f'_parte{i+1}.pdf')
            with open(caminho_parte, 'wb') as f:
                writer.write(f)

        # Exclui o arquivo original após a divisão
        os.remove(caminho_pdf)
        print(f"PDF {caminho_pdf} dividido em {partes_necessarias} parte(s) com sucesso.")
        
    except Exception as e:
        print(f"Erro ao dividr pdf {caminho_pdf} erro: {e}")
        logs.error(f"Erro ao dividr pdf {caminho_pdf} erro: {e}")
   
def converter_para_docx(arquivo_origem):
    nome_arquivo_sem_extensao, ext = os.path.splitext(arquivo_origem)
    novo_arquivo_docx = f"{nome_arquivo_sem_extensao}.docx"

    try:
        if ext.lower() == ".doc":
            # Usa LibreOffice para converter .doc em .docx
            subprocess.run([
                "soffice", "--headless", "--convert-to", "docx", arquivo_origem, "--outdir", os.path.dirname(arquivo_origem)
            ], check=True)
            print(f"Convertido {arquivo_origem} para {novo_arquivo_docx} usando LibreOffice")
            logs.info(f"Convertido {arquivo_origem} para {novo_arquivo_docx} usando LibreOffice")
        else:
            # Usa pypandoc para outros formatos válidos (ex: .md, .odt, .txt, etc)
            pypandoc.convert_file(arquivo_origem, 'docx', outputfile=novo_arquivo_docx)
            print(f"Convertido {arquivo_origem} para {novo_arquivo_docx} com Pandoc")
            logs.info(f"Convertido {arquivo_origem} para {novo_arquivo_docx} com Pandoc")
    except Exception as e:
        print(f"Erro ao converter {arquivo_origem} para DOCX: {e}")
        logs.error(f"Erro ao converter {arquivo_origem} para DOCX: {e}")



## PROCESSOS PARA LICITAÇÕES QUE JA EXISTEM EM BANCO DE DADOS   

def executar_processos_alteracao(processo, notificacao_config):
    try:   
        ids_usuarios = notificacao_config['ids_usuarios']
        plataforma = notificacao_config['plataforma']
        urlBase =  notificacao_config['url']
        driver = None
        driver, profile_dir = criar_driver(mostrar_browser = False)
        driver.get(urlBase)
        
        controles_iniciais(driver)
        # Obter novos dados
        novos_dados = extrair_dados_nova_pagina_alteracao(processo, driver)

        # Garantir que dados_existentes seja uma lista ou dicionário
        dados_existentes = retornar_edital_existente_by_plataforma(processo, plataforma)
        dados_existentes = dados_existentes[0] if isinstance(dados_existentes, list) and dados_existentes else {}
        dados_existentes.update(processo)
        
         # Mapeamento para normalizar chaves
        mapeamento_chaves = {
            'QuantidadeItens': 'quantidade_total_itens',
            'DataFimRecebimentoProposta': 'data_fim_recebimento_proposta',
            'CodigoUnidadeCompradora': 'codigo_unidade_compradora',
            'Situação': 'situacao',
            'ValorTotalEstimadoCompra': 'valor_total_estimado_compra',
            'Numero': 'numero',
            'IdContratacaoPncp': 'id_contratacao_pncp',
            'Licitacao': 'licitacao',
            'Orgao': 'orgao',
            'Municipio': 'municipio',
            'Uf': 'uf',
            'Cnpj': 'cnpj',
            'Link': 'link',
        }
        
        novos_dados_filtrados = {
        mapeamento_chaves[k]: v for k, v in novos_dados.items() if k in mapeamento_chaves
        }

        dados_existentes_filtrados = {
         k: v for k, v in dados_existentes.items() if k in mapeamento_chaves.values()
        }

        # Normalizar as chaves para comparação
        novos_dados_normalizados = {k.lower(): v for k, v in novos_dados_filtrados.items()}
        dados_existentes_normalizados = {k.lower(): v for k, v in dados_existentes_filtrados.items()}

      # Ajustar o CNPJ antes da comparação
        if 'cnpj' in novos_dados_normalizados:
            novos_dados_normalizados['cnpj'] = limpar_cnpj(novos_dados_normalizados['cnpj'])
        if 'cnpj' in dados_existentes_normalizados:
            dados_existentes_normalizados['cnpj'] = limpar_cnpj(dados_existentes_normalizados['cnpj'])
            
            
        alteracoes = {
            chave: {"antes": valor_existente, "depois": novo_valor}
            for chave, novo_valor in novos_dados_normalizados.items()
            if (valor_existente := dados_existentes_normalizados.get(chave)) != novo_valor
        }

        arquivos_baixados = acao_baixar_arquivo_alteracao(processo, driver)
        if arquivos_baixados > 0:
            alteracoes["status_processo_arquivos"] = "Novos arquivos encontrados"
            alteracoes["arquivosBaixados"] = arquivos_baixados
        
        if alteracoes:
           edital = gravar_alteracao_processo(alteracoes, dados_existentes)
            
        if alteracoes or arquivos_baixados > 0:
            edital.update(novos_dados)
            ##enviar_mensagem(edital, ids_usuarios, novo_processo=False, plataforma=plataforma)
            
        if alteracoes:     
          return{"resultado": edital}
        else:
            print("Nenhuma alteração detectada.")

    except Exception as e:
        print(f"Erro ao executar os processos de alteração: {e}")
  
    
def extrair_dados_nova_pagina_alteracao(editeditalalteracaoal, driver): 
    tentativas = 4
    try:  
        driver.execute_script("window.open(arguments[0], '_blank');", editeditalalteracaoal["link"])
        driver.switch_to.window(driver.window_handles[-1])
        
        for tentativa in range(tentativas):    
            try:
                elementos_nova_pagina = driver.find_elements(By.XPATH, '//div[@id="main-content"]/pncp-item-detail/div')
                texto = elementos_nova_pagina[0].text
                match = re.search(r'(\d+)\s+itens', texto)
                numero_itens = match.group(1) if match else '0'
                id_aux = extrair_texto(texto, 'Id contratação PNCP: ')
                
                novos_campos = {
                    'QuantidadeItens': numero_itens,
                    'DataInicioRecebimentoProposta': extrair_data_com_horario(texto, 'Data de início de recebimento de propostas: ') or None,
                    'DataFimRecebimentoProposta': extrair_data_com_horario(texto, 'Data fim de recebimento de propostas: ') or None,
                    'CodigoUnidadeCompradora': extrair_codigo_unidade_compradora(texto),
                    'ModoDeDisputa': extrair_texto(texto, 'Modo de disputa: '),
                    'Tipo': extrair_texto(texto, 'Tipo: '),
                    'Situacao':extrair_texto(texto, 'Situação: '),
                    'Numero': f"{int(id_aux.split('-')[2].split('/')[0])}/{id_aux.split('/')[-1]}",
                    'IdContratacaoPncp': id_aux,
                    'Licitacao': extrair_texto(texto, 'Modalidade da Contratação: '),
                    'Data': extrair_texto(texto, 'Última Atualização: '),
                    'Orgao': extrair_texto(texto, 'Órgão: '),
                    'Municipio': extrair_texto(texto, 'Local: '),
                    'Uf': extrair_texto(texto, 'Local: ').split('/')[1],
                    'Descricao': extrair_texto(texto, 'Objeto:'),
                    'Cnpj': id_aux.split('-')[0],
                }
                
                button = "Acessar Contratação" in texto
            
                elemento_valor_total = elementos_nova_pagina[0].find_elements(By.XPATH, './/div[8]')
            
                if elemento_valor_total:
                    texto = elemento_valor_total[0].text
                    novos_campos['ValorTotalEstimadoCompra'] = extrair_texto(texto, 'VALOR TOTAL ESTIMADO DA COMPRA\n')
                    
                  # Só agora, no final, tenta abrir o link do botão em nova aba e capturar a URL
                link = None
                
                if button:
                    try:
                        botao = elementos_nova_pagina[0].find_element(By.XPATH, './/div[1]/div[2]/div/button')
                        
                        janela_antes = driver.window_handles
                        botao.click()

                        WebDriverWait(driver, 20).until(lambda d: len(d.window_handles) > len(janela_antes))
                        nova_janela = [w for w in driver.window_handles if w not in janela_antes][0]
                        driver.switch_to.window(nova_janela)

                        link = driver.current_url

                        driver.close()
                        driver.switch_to.window(janela_antes[-1])

                    except NoSuchElementException:
                        pass
                    except TimeoutException:
                        print("Timeout esperando mudança após clique no botão")
                    except Exception as e:
                        print("Erro ao tentar abrir link do botão:", e)

                if link:
                    novos_campos['LinkBotao'] = link
                            
            
            except Exception as e:
                if tentativa < tentativas - 1:
                    print(f"Erro na tentativa extrair_dados_nova_pagina_alteracao {tentativa + 1}: {e}. Tentando novamente...")
                    time.sleep(2)  
                else:
                    print(f"Erro na tentativa extrair_dados_nova_pagina_alteracao final: {e}")
                    return None     
            
            finally:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])    
            
            return novos_campos
 
    except Exception as e:
        logs.error("extrair_dados_nova_pagina_alteracao error pegar dados arquivos - ", str(e))
       
         
def acao_baixar_arquivo_alteracao(edital, driver):
    tentativas = 2
    for tentativa in range(tentativas):
     try:
        driver.execute_script("window.open(arguments[0], '_blank');", edital["Link"])
        driver.switch_to.window(driver.window_handles[-1])
        
        try:
            elemento = driver.find_element(By.XPATH, '//*[@id="main-content"]/pncp-item-detail/div/pncp-tab-set/div/pncp-tab[2]/div/div/pncp-table/div/ngx-datatable/div/datatable-body/datatable-selection/datatable-scroller')
            rows = elemento.find_elements(By.CSS_SELECTOR, "datatable-row-wrapper")
            arquivos =[]
            for row in rows:
                nome = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(1) span").get_attribute("innerText").strip()
                data = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(2) div").get_attribute("innerText").strip()
                tipo = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(3) span").get_attribute("innerText").strip()
                link = row.find_element(By.CSS_SELECTOR, "datatable-body-cell:nth-child(4) a").get_attribute("href")
                arquivos.append({
                 "nome": nome,
                 "data": data,
                 "tipo": tipo,
                 "link": link
                })
                      
            arquivos_baixados = salvar_arquivos_alteracao(arquivos, edital)
             
        except Exception as dArq:
                logs.error("Erro acao_baixar_arquivo_alteracao - ", str(dArq))
        finally:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])  
            
        return arquivos_baixados 
    
     except Exception as dArq:
        if tentativa < tentativas - 1:
            print(f"Erro na tentativa acao_baixar_arquivo_alteracao {tentativa + 1}: {dArq}. Tentando novamente...")
            time.sleep(2) 
        else: 
            logs.error("Erro na tentativa acao_baixar_arquivo_alteracao final - ", str(dArq))
            return 0  # Retorna 0 se ocorrer error
        
             
def salvar_arquivos_alteracao(arquivos, edital):
    try:
        locale.setlocale(locale.LC_TIME, "Portuguese_Brazil.1252")
        # Obter datas
        hoje = datetime.today().strftime("%Y-%m-%d")
        ano_atual = datetime.today().strftime("%Y")
        mes_atual = datetime.today().strftime("%B").capitalize() 
       
        # Limpar caracteres inválidos do número do edital e nome do órgão
        numero_edital = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Numero", "Desconhecido")).strip())
        orgao_edital = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Orgao", "Desconhecido")).strip())
           
        pasta_downloads = str(Path.home() / "Downloads")
        # Caminho base do edital
        pasta_base = os.path.join(pasta_downloads, f"SEGURO/{ano_atual}/{mes_atual}/Edital{numero_edital}.{orgao_edital}")
        pasta_data = os.path.join(pasta_base, hoje)
        
        # Criar apenas a pasta do dia se a base já existir
        if not os.path.exists(pasta_base):
            os.makedirs(pasta_base)  # Criar toda a estrutura
            print(f"Criado diretório base: {pasta_base}")
        if not os.path.exists(pasta_data):
            os.makedirs(pasta_data)  # Criar apenas a pasta do dia
            print(f"Criado diretório para data {hoje}")
            
        arquivos_existentes = [f for f in os.listdir(pasta_data) if f.endswith(".pdf")]

        existeTipoEdital = False
       
        for arquivo in arquivos_existentes:
            match = re.match(r"(\d+)-", arquivo)  # Captura o número antes do "-"
            if match:
                numero = int(match.group(1))
                if numero == 1:
                    existeTipoEdital = True
               
        quantidade = sum(1 for arquivo in arquivos if arquivo.get("tipo") == "edital")
        arquivos_baixados = 0
        
        for arquivo in arquivos:
            tipo = arquivo.get("tipo")
            nome = re.sub(r'[\\/:*?"<>|]', '_', str(arquivo.get("nome", "Desconhecido")).strip())  
             
            if "edital" in tipo.lower(): 
                if quantidade > 1 or existeTipoEdital:   
                    nome_arquivo = f"1-{nome}.pdf"
                else:
                    nome_arquivo = f"1-Edital.pdf"                
            else:
                nome_arquivo = f"{nome}.pdf"
                
            caminho_completo = os.path.join(pasta_data, nome_arquivo)
            
            if os.path.exists(caminho_completo):
                print(f"O arquivo {nome_arquivo} já existe no caminho {caminho_completo}.")
            else:
            # Baixar o arquivo
                response = requests.get(arquivo["link"], stream=True)
                if response.status_code == 200:
                    with open(caminho_completo, "wb") as file:
                        shutil.copyfileobj(response.raw, file)
                    arquivos_baixados += 1
                    print(f"Arquivo salvo: {caminho_completo}")
                else:
                    print(f"Erro ao baixar {arquivo['link']}")
                    
        return arquivos_baixados  # Retorna a quantidade de arquivos baixados            

    except Exception as e:
        logs.error("Erro ao salvar arquivos - ", str(e))
        return 0  # Retorna 0 em caso de error