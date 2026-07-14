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
from pncp_shared.metadata.controle_metadados import ControleMetadados
from pncp_shared.utils.drivers import criar_driver, finalizar_driver, acessar_url, controles_iniciais
from pncp_shared.logs.controle_logs import (
    logs,
    controle_logs,   
)
from pncp_shared.config.controle_config import(
    configuracoes, 
    carregar_configuracoes,
    atualizar_arquivo_configuracoes
    ) 

from pncp_shared.database.repositoriopncp import (
    retornar_registro_paginas,
    retornar_termos_busca_by_id_page,
    retornar_qtd_registros_heuristica_busca,
    atualizar_heuristica,
    atualizar_heuristica_busca,
    atualizar_ultima_data,
    salvar_urls_com_erro_api
)
from pncp_shared.utils.funcoespncp import limpar_console
from pncp_bot_seguro.services.processamento_edital import processar_texto

from threading import Lock
import ollama

lock_pos_login = Lock()
editais_em_processamento = set()
lock_editais = Lock()

retornoMsg = ""

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
    lista_erros_api = []

    try: 
        if url.strip() == "":
            logs.error("A URL está vazia")
            return
        
        filtros_base = carregar_filtros(filtros)
        if "banco" not in filtros_base:
            filtros_base["banco"] = {}
        if "palavraschave" not in filtros_base["banco"]:
            filtros_base["banco"]["palavraschave"] = {}
        url_base = url

        while True:
            hora_atual = datetime.now().hour
            processar_dia = configuracoes.get('processar_dia')
            controle_logs()
            
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
                total_processados = processar_pagina(driver, url_base, filtros_base, id_pagina, ids_usuarios,lista_elementos, plataforma, total_processados, 
                    quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp, lista_erros_api)
                
                atualizar_ultima_data(id_pagina)
                filtros_base["banco"]["qtd_registros"] = retornar_registro_paginas(id_pagina, 4)

                #Limpar console a cada 10 minutos
                if time.time() - ultima_limpeza >= 600:
                    limpar_console()
                    carregar_configuracoes(plataforma)
                    ultima_limpeza = time.time()  

                print("\nAguardando novos processos...\n")
            
            except Exception as e_conectar:
                logs.error(f"Erro ao conectar/processar URL '{url_base}': {e_conectar}", exc_info=True)
                time.sleep(2)  # Espera 2 segundos antes de tentar novamente

            finally:
                try:
                    if lista_erros_api:
                        salvar_urls_com_erro_api(lista_erros_api, id_pagina=id_pagina, plataforma=plataforma)
                except Exception as e:
                    logs.error(f"Erro ao salvar lista_erros_api: {e}", exc_info=True)
                
                finalizar_driver(driver, profile_dir, contexto="driver PNCP Seguro")
      
            time.sleep(0.1)
          
    except Exception as e_crawler:
        logs.error(f"Erro fatal no crawler: {str(e_crawler)}")

     
def processar_pagina(driver, urlBase, filtrosBase, id_pagina, ids_usuarios, listaElementos, plataforma, total_processados, 
                     quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp, lista_erros_api):
    try:
        lista_planilha = []
        controles_iniciais(driver)

        pagination_info = driver.find_elements(By.CLASS_NAME, "pagination-information")
        if not pagination_info:
            print("Nenhum elemento de paginação encontrado.\n")
            return total_processados

        match = re.search(r'(\d+)(?=\s*itens)', pagination_info[0].text.strip())
        if not match:
            return total_processados
    
        total_itens = total_itens_tmp if total_itens_tmp > 0 else int(match.group(1))
        registros = int(filtrosBase["banco"].get("qtd_registros", 0) or 0)

        if  total_itens == registros:
            print(f"Execução interrormpida pelo processo de Heurística - {registros}/{total_itens}\n")
            return total_processados
        
        retorno_elemento = driver.find_elements(By.CLASS_NAME, value='br-list')
        listaElementos.append(retorno_elemento[:])
        
        if not listaElementos or not listaElementos[-1]:
            return total_processados
        
        posicao_index_atual = [1]
        retorno_elemento += listaElementos[-1][posicao_index_atual[-1]].find_elements(By.CLASS_NAME, value='br-item')
        listaElementos.append(retorno_elemento[:])
        
        if len(listaElementos) < 2 or not listaElementos[1]:
            return total_processados

        novalistaElementos = [el.text for el in listaElementos[1][4:] if el.text.strip() != '']
        if not novalistaElementos:
            return total_processados

        palavra_chave = list(filtrosBase['banco']['palavraschave'].keys())[0].strip().lower()
        
        quantidade_para_processar, processa_mais_paginas, total_itens_tmp, processar_todos = calcular_quantidade_para_processar(
            total_itens, registros, quantidade_para_processar, processar_dia, hora_atual, palavra_chave
        )
            
        error_timeout = 0
       
        for texto in islice(novalistaElementos, quantidade_para_processar):
            total_processados += 1
            print(f"PROCESSANDO N°: {total_processados} / TOTAL A SER PROCESSADO: {quantidade_para_processar}")
            
            edital, error_timeout= processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, 
                processar_dia,filtrosBase, lock_editais, editais_em_processamento, error_timeout, lista_erros_api)
            
            if edital:
                lista_planilha.append(copy.deepcopy(edital))
                               
        ##if len(lista_planilha) > 0:
            ##print(f"Processando Planilhas...\n")
            ##gerar_excel_registros(lista_planilha, plataforma, True) 
            ##time.sleep(1)
                
        if processar_todos or processa_mais_paginas:
            return processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, filtros, 
                notificacao_config, filtrosBase, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp, lista_erros_api)
                    
        atualizar_heuristica(id_pagina, total_itens) 
        return total_processados
        
    except Exception as e:
        logs.error(f"Erro no processamento da página: {e}\n")
        return total_processados


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

def processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, filtros, notificacao_config,
                                  filtrosBase, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp, lista_erros_api): 
    try:
        print(f"Total Processados {palavra_chave}: {total_processados}/ Total a processar {palavra_chave}: {quantidade_para_processar}\n")
        logs.info(f"Total Processados {palavra_chave}: {total_processados}/ Total a processar {palavra_chave}: {quantidade_para_processar}\n")

        while total_processados < quantidade_para_processar:
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

            processar_pagina(driver, urlBase, filtrosBase, id_pagina, ids_usuarios, listaElementos, plataforma, total_processados, quantidade_para_processar,
                           pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp, lista_erros_api)

        atualizar_heuristica(id_pagina, total_itens_tmp) 
        carregar_configuracoes()
        filtros["banco"]["qtd_registros"] = retornar_registro_paginas(id_pagina, 4)
        crawler(urlBase, filtros, notificacao_config)
        return total_processados
    except Exception as e:
        logs.error(f"Erro no processamento processar_paginas_adicionais: {e}\n")
        return total_processados
