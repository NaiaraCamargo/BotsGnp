# Imports da biblioteca padrão
import re
import time
import copy
from itertools import islice
from datetime import datetime

# Imports de bibliotecas externas
from selenium.webdriver.common.by import By
from threading import Lock

# Imports de módulos locais
from pncp_shared.utils.drivers import criar_driver, finalizar_driver, acessar_url, controles_iniciais, navegar_url_pncp
from pncp_shared.logs.controle_logs import (
    logs,
    controle_logs,   
)
from pncp_shared.config.controle_config import(
    configuracoes, 
    carregar_configuracoes,
    ) 

from pncp_shared.database.repositoriopncp import (
    retornar_buscas_adicionais,
    retornar_registro_paginas,
    atualizar_heuristica,
    atualizar_heuristica_busca_filtro,
    atualizar_ultima_data,
    salvar_urls_com_erro_api
)
from pncp_shared.utils.funcoespncp import limpar_console
from pncp_shared.utils.urls_pncp import aplicar_parametros_url, definir_pagina_pncp
from pncp_bot_seguro.services.processamento_edital import processar_texto

lock_pos_login = Lock()
editais_em_processamento = set()
lock_editais = Lock()

retornoMsg = ""

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

        while True:
            hora_atual = datetime.now().hour
            processar_dia = configuracoes.get('processar_dia')
            controle_logs()
            driver, profile_dir = None, None
            url_base = url

            try:
                driver, profile_dir = criar_driver(mostrar_browser)

                qtd_padrao = retornar_registro_paginas(id_pagina, 4)
                buscas = [{
                    "id": None,
                    "nome": "padrao",
                    "url": url,
                    "qtd_registros": int(qtd_padrao or 0),
                }]

                for busca_adicional in retornar_buscas_adicionais(id_pagina):
                    buscas.append({
                        "id": busca_adicional["id"],
                        "nome": busca_adicional["nome"],
                        "url": aplicar_parametros_url(
                            url,
                            busca_adicional["parametros_url"]
                        ),
                        "qtd_registros": int(busca_adicional["qtd_registros"] or 0),
                    })

                for busca in buscas:
                    url_base = busca["url"]
                    filtros_execucao = copy.deepcopy(filtros_base)
                    filtros_execucao["banco"]["qtd_registros"] = busca["qtd_registros"]

                    acessar_url(driver, url_base, plataforma, processar_dia, hora_atual)

                    lista_elementos.clear()
                    print(f"\nIniciando busca: {busca['nome']} | URL: {url_base}\n")

                    total_processados = processar_pagina(
                        driver, url_base, filtros_execucao, id_pagina,
                        ids_usuarios, lista_elementos, plataforma, 0, 0, 2,
                        processar_dia, hora_atual, filtros_execucao,
                        notificacao_config, 0, lista_erros_api, busca["id"]
                    )

                    if busca["id"] is None:
                        atualizar_ultima_data(id_pagina)

                    logs.info(
                        f"[CRAWLER SEGURO] Finalizada busca='{busca['nome']}' "
                        f"total_processados={total_processados}"
                    )

                    if time.time() - ultima_limpeza >= 600:
                        limpar_console()
                        carregar_configuracoes(plataforma)
                        ultima_limpeza = time.time()

                print("\nAguardando novos processos...\n")

            except Exception as e_conectar:
                logs.error(f"Erro ao conectar/processar URL '{url_base}': {e_conectar}", exc_info=True)
                time.sleep(5)

            finally:
                try:
                    if lista_erros_api:
                        salvar_urls_com_erro_api(
                            lista_erros_api,
                            id_pagina=id_pagina,
                            plataforma=plataforma
                        )
                except Exception as e:
                    logs.error(f"Erro ao salvar lista_erros_api: {e}", exc_info=True)

                finalizar_driver(driver, profile_dir, contexto="driver PNCP Seguro")

            return

    except Exception as e_crawler:
        logs.error(f"Erro fatal no crawler: {str(e_crawler)}")

     
def processar_pagina(driver, urlBase, filtrosBase, id_pagina, ids_usuarios, listaElementos, plataforma, total_processados, 
                     quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp,
                     lista_erros_api, id_busca=None):
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

        if id_busca is None and total_itens == registros:
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
        
        if id_busca is not None:
            quantidade_revisao = int(configuracoes.get("quantidade_revisao_buscas_adicionais", 20) or 20)
            quantidade_para_processar = min(max(quantidade_revisao, 1), total_itens)
            processa_mais_paginas, total_itens_tmp, processar_todos = False, total_itens, False
            logs.info(f"Busca adicional {id_busca}: revisando os {quantidade_para_processar} resultados mais recentes.")
        else:
            quantidade_para_processar, processa_mais_paginas, total_itens_tmp, processar_todos = calcular_quantidade_para_processar(
                total_itens, registros, quantidade_para_processar, processar_dia, hora_atual, palavra_chave)
            
        error_timeout = 0
       
        for texto in islice(novalistaElementos, quantidade_para_processar):
            total_processados += 1
            print(f"PROCESSANDO N°: {total_processados} / TOTAL A SER PROCESSADO: {quantidade_para_processar}")
            
            edital, error_timeout = processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual,
                processar_dia, filtrosBase, lock_editais, editais_em_processamento, error_timeout, lista_erros_api, id_busca)
            
            if edital:
                lista_planilha.append(copy.deepcopy(edital))
                               
        ##if len(lista_planilha) > 0:
            ##print(f"Processando Planilhas...\n")
            ##time.sleep(1)
                
        if processar_todos or processa_mais_paginas:
            return processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, filtros, 
                notificacao_config, filtrosBase, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp,
                lista_erros_api, id_busca)

        atualizar_heuristica_execucao(id_pagina, id_busca, total_itens)
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


def atualizar_heuristica_execucao(id_pagina, id_busca, total_itens):
    if id_busca is None:
        atualizar_heuristica(id_pagina, total_itens)
    else:
        atualizar_heuristica_busca_filtro(id_busca, total_itens)


def processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, filtros, notificacao_config,
                                  filtrosBase, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp,
                                  lista_erros_api, id_busca=None):
    try:
        print(f"Total Processados {palavra_chave}: {total_processados}/ Total a processar {palavra_chave}: {quantidade_para_processar}\n")
        logs.info(f"Total Processados {palavra_chave}: {total_processados}/ Total a processar {palavra_chave}: {quantidade_para_processar}\n")

        while total_processados < quantidade_para_processar:
            url = definir_pagina_pncp(urlBase, pagina)
            print(f"Iniciando processamento da palavra_chave: {palavra_chave} na página: {pagina} url: {url}\n")
            logs.info(f"Iniciando processamento da palavra_chave: {palavra_chave} na página: {pagina} url: {url}\n")

            navegar_url_pncp(driver, url)
            listaElementos = []

            total_antes = total_processados
            total_processados = processar_pagina(driver, urlBase, filtrosBase, id_pagina, ids_usuarios,
                listaElementos, plataforma, total_processados, quantidade_para_processar, pagina, processar_dia, hora_atual,
                filtros, notificacao_config, total_itens_tmp, lista_erros_api,id_busca
            )

            if total_processados == total_antes:
                logs.info(
                    f"Sem avanço na página {pagina} da busca '{palavra_chave}'. "
                    "Encerrando paginação."
                )
                break

            pagina += 1

        atualizar_heuristica_execucao(id_pagina, id_busca, total_itens_tmp)
        carregar_configuracoes(plataforma)
        return total_processados
    except Exception as e:
        logs.error(f"Erro no processamento processar_paginas_adicionais: {e}\n")
        return total_processados
