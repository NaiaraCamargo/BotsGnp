import re
from itertools import islice
from datetime import datetime
from threading import Lock

from selenium.webdriver.common.by import By

from pncp_shared.metadata.controle_metadados import ControleMetadados
from pncp_shared.utils.drivers import criar_driver, finalizar_driver, acessar_url, controles_iniciais
from pncp_shared.logs.controle_logs import (
    logs,
    controle_logs,   
)
from pncp_shared.config.controle_config import(
    configuracoes, 
    carregar_configuracoes
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
from pncp_bot_obra.services.processamento_edital import processar_texto
from pncp_shared.utils.urls_pncp import gerar_urls_variantes_pncp

lock_pos_login = Lock()
editais_em_processamento = set()
lock_editais = Lock()
            
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
    lista_erros_api = []
    id_plataforma = 4       

    try: 
        if url.strip() == "":
            logs.error("A URL está vazia")
            return
        
        filtros_base = carregar_filtros(filtros)
        if "banco" not in filtros_base:
            filtros_base["banco"] = {}
        if "palavraschave" not in filtros_base["banco"]:
            filtros_base["banco"]["palavraschave"] = {}
            
        termos_variantes = retornar_termos_busca_by_id_page(id_pagina)
        urls_para_processar, termo_orignal = gerar_urls_variantes_pncp(url, termos_variantes)

        hora_atual = datetime.now().hour
        processar_dia = configuracoes.get('processar_dia')
        controle_logs()
        
        driver, profile_dir = None, None
        
        try:            
            driver, profile_dir = criar_driver(mostrar_browser)
            processou_original = False
            
            for item_url in urls_para_processar:
                url_base = item_url["url"]
                termo_busca = item_url["termo_busca"]
                
                try:
                    if termo_busca == termo_orignal:
                        processou_original = True
                        filtros_base["banco"]["qtd_registros"] = retornar_registro_paginas(id_pagina, id_plataforma)
                    else:
                        filtros_base["banco"]["qtd_registros"] = retornar_qtd_registros_heuristica_busca(id_pagina, id_plataforma, termo_busca)
                    
                    acessar_url(driver, url_base, plataforma, processar_dia, hora_atual)
                    
                    lista_elementos.clear()
                    total_processados = 0
                    quantidade_para_processar = 0
                    pagina = 2
                    total_itens_tmp = 0

                    print(f"\nIniciando processamento do termo: {termo_busca} | URL: {url_base}\n")
                    total_processados = processar_pagina(driver, url_base, filtros_base, id_pagina, ids_usuarios, lista_elementos, plataforma, total_processados, 
                                        quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp, lista_erros_api,
                                        termo_busca, id_plataforma, termo_orignal)
                
                    logs.info(f"[CRAWLER] Finalizado termo='{termo_busca}' total_processados={total_processados}")

                except Exception as e_variante:
                    logs.error(f"Erro ao processar variante termo='{termo_busca}' url='{url_base}': {e_variante}", exc_info=True)
                    continue
                
            if processou_original:
                atualizar_ultima_data(id_pagina)
                   
            print("Ciclo concluído.\n")        
            return 
        
        except Exception as e_conectar:
            logs.error(f"Erro ao conectar/processar URL '{url_base}': {e_conectar}", exc_info=True)
            raise

        finally:
            try:
                if lista_erros_api:
                    salvar_urls_com_erro_api(lista_erros_api, id_pagina=id_pagina, plataforma=plataforma)
            except Exception as e:
                logs.error(f"Erro ao salvar lista_erros_api: {e}", exc_info=True)
            finalizar_driver(driver, profile_dir, contexto="driver PNCP Obras")
          
    except Exception as e_crawler:
        logs.error(f"Erro fatal no crawler: {str(e_crawler)}")
        raise

def processar_pagina(driver, urlBase, filtros_base, id_pagina, ids_usuarios, listaElementos, plataforma, total_processados, quantidade_para_processar, 
                    pagina, processar_dia, hora_atual, filtros, notificacao_config, total_itens_tmp, lista_erros_api, 
                    termo_busca, id_plataforma, termo_original):
    try:
        controles_iniciais(driver)

        pagination_info = driver.find_elements(By.CLASS_NAME, "pagination-information")
        if not pagination_info:
            print("Nenhum elemento de paginação encontrado.\n")
            return total_processados

        match = re.search(r'(\d+)(?=\s*itens)', pagination_info[0].text.strip())
        if not match:
            return total_processados
    
        total_itens = total_itens_tmp if total_itens_tmp > 0 else int(match.group(1))
        registros = int(filtros_base["banco"].get("qtd_registros", 0) or 0)

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
        
        palavra_chave = list(filtros_base['banco']['palavraschave'].keys())[0].strip().lower()
        
        quantidade_para_processar, processa_mais_paginas, total_itens_tmp, processar_todos = calcular_quantidade_para_processar(
            total_itens, registros, quantidade_para_processar, processar_dia, hora_atual, palavra_chave
        )
            
        error_timeout = 0
        try:
            for texto in islice(novalistaElementos, quantidade_para_processar):
                total_processados += 1
                print(f"PROCESSANDO N°: {total_processados} / TOTAL A SER PROCESSADO: {quantidade_para_processar}")
                
                edital, error_timeout= processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, 
                    processar_dia,filtros_base, lock_editais, editais_em_processamento, error_timeout, lista_erros_api, termo_busca)

        except Exception as e:
            logs.error(f"Erro no processamento: {e}\n")    
                
        if processar_todos or processa_mais_paginas:
            return processar_paginas_adicionais(driver, urlBase, palavra_chave, total_processados, quantidade_para_processar, pagina, filtros, 
                notificacao_config, filtros_base, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp, 
                lista_erros_api, termo_busca, id_plataforma, termo_original)
        
        if termo_busca == termo_original:
            atualizar_heuristica(id_pagina, total_itens)
        else:            
            atualizar_heuristica_busca(id_pagina, id_plataforma, termo_busca or "sem_termo", total_itens)
            
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
                                filtros_base, plataforma, processar_dia, hora_atual, id_pagina, ids_usuarios, total_itens_tmp,
                                lista_erros_api, termo_busca, id_plataforma, termo_original):
    try:
        print(f"Total Processados {termo_busca}: {total_processados}/ Total a processar {termo_busca}: {quantidade_para_processar}\n")
        logs.info(f"Total Processados {termo_busca}: {total_processados}/ Total a processar {termo_busca}: {quantidade_para_processar}\n")

        while total_processados < quantidade_para_processar:
            url = urlBase.replace('&pagina=1', f'&pagina={pagina}')
            print(f"Iniciando processamento da palavra_chave: {termo_busca} na página: {pagina} url: {url}\n")
            logs.info(f"Iniciando processamento da palavra_chave: {termo_busca} na página: {pagina} url: {url}\n")

            driver.get(url)
            listaElementos = []
            
            total_antes = total_processados
            
            total_processados = processar_pagina(driver, urlBase, filtros_base, id_pagina, ids_usuarios, listaElementos, plataforma, total_processados,
                            quantidade_para_processar, pagina, processar_dia, hora_atual, filtros, notificacao_config,
                            total_itens_tmp,lista_erros_api, termo_busca, id_plataforma, termo_original)
            
            if total_processados == total_antes:
                print(f"Sem avanço na página {pagina}. Encerrando para evitar looping.\n")
                logs.info(f"Sem avanço na página {pagina}. Encerrando para evitar looping.\n")
                break

            pagina += 1
        
        if termo_busca == termo_original:
            atualizar_heuristica(id_pagina, total_itens_tmp)
        else:
            atualizar_heuristica_busca(id_pagina, id_plataforma, termo_busca or "sem_termo", total_itens_tmp)
        carregar_configuracoes(plataforma)
        try:
            if termo_busca == termo_original:
                filtros["banco"]["qtd_registros"] = retornar_registro_paginas(id_pagina)
            else:
                filtros["banco"]["qtd_registros"] = retornar_qtd_registros_heuristica_busca(id_pagina, id_plataforma, termo_busca)
        except Exception:
            pass
        
        return total_processados
    except Exception as e:
        logs.error(f"Erro no processamento processar_paginas_adicionais: {e}\n")
        return total_processados
        



