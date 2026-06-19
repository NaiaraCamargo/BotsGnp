from datetime import datetime
import time

from pncp_shared.api.api_arquivos import buscar_arquivos, salvar_arquivos_api
from pncp_shared.utils.funcoespncp import obter_pastas_download
from pncp_shared.logs_pncp.controle_logs import logs
from pncp_shared.controllers.controle_envio_TG import enviar_mensagem
from pncp_shared.database.repositoriopncp import verificar_existencia_edital_new, gravar_novo_processo
from pncp_shared.utils.validadores_pncp import (
    validar_palavras,
    extrair_chaves_do_link,
    extrair_texto,
)
from pncp_bot_material_escolar.api.api_edital import (
    buscar_compra_e_itens, 
    codigos_unicos_do_edital, 
    montar_novos_campos, 
    montar_itens_campos
)

def processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, processar_dia, filtrosBase, lock_editais, 
                    editais_em_processamento, error_timeout, lista_erros_api=None):
    
    palavras_destacadas = validar_palavras(texto=texto, filtrosBase=filtrosBase)

    edital = extrair_link(texto, urlBase)
    link = edital.get("Link", "").strip()

    with lock_editais:
        if link in editais_em_processamento:
            print(f"[IGNORADO - EM PROCESSAMENTO] {link}\n")
            return None, error_timeout
        editais_em_processamento.add(link)

    try:
        palavras_limpa = [p.strip("'\"") for p in palavras_destacadas if p.strip("'\"")]
        edital["palavras_chave"] = palavras_limpa if palavras_limpa else ""

        edital.update({
            "id_pagina": id_pagina,       
            "notificar_retorno": True,
            "envio_notificacao": datetime.now()
        })

        resultadoExisteEdital = verificar_existencia_edital_new(edital["Link"])
        if resultadoExisteEdital:
            print(f"EDITAL JA EXISTE NO BANCO: {resultadoExisteEdital[0]['link']}\n")
            logs.info(f"Edital já existe no banco: {resultadoExisteEdital[0]['id']} - {resultadoExisteEdital[0]['link']}\n")
            return None, error_timeout
        
        edital, error_timeout = processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtrosBase, plataforma, lista_erros_api)

        return edital, error_timeout
    except Exception as e:
        logs.error(f"[ERRO AO PROCESSAR TEXTO] {link} - {e}")
    finally:
        with lock_editais:
            editais_em_processamento.discard(link)

    return None, error_timeout

def processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtrosBase, plataforma, lista_erros_api):
    
    try:    
        link = edital["Link"]
        chaves = extrair_chaves_do_link(link)
        
        if not chaves:
            print(f"[LINK INVÁLIDO PNCP] {link} \n")
            logs.error(f"[LINK INVÁLIDO PNCP] {link}\n")
            return None, error_timeout

        cnpj, ano, numero = chaves
        
        compra, qtd_items, itens, falhou_por_timeout  = tentar_buscar_compra(cnpj, ano, numero, link, lista_erros_api, max_tentativas=3)

        if compra is None:
            if falhou_por_timeout:
                return tratar_timeout(edital, error_timeout, ids_usuarios)
            
            return None, error_timeout

        error_timeout = 0
        
        novos_dados = montar_novos_campos(compra, qtd_items, link, palavras_destacadas)
        
        itens_dados = montar_itens_campos(link, itens or [])
        edital["itens_dados"] = itens_dados
        
        codigos_catalogo = codigos_unicos_do_edital(itens_dados)
        edital["codigos_catalogo"] = codigos_catalogo
        
        palavra_chave_item = bool(codigos_catalogo)
        
        edital["itens_validos"] = [i for i in itens_dados if i.get("itemValidoCatalogo")]
        
        if not palavras_destacadas and not palavra_chave_item:
            print(" NENHUMA PALAVRA CHAVE ENCONTRADA NO OBJETO E NOS ITENS\n")
            return None, error_timeout

        edital.update(novos_dados)
        
        pasta_killer, pasta_comprimidos = obter_pastas_download(edital, plataforma)
        edital["pasta_download"] = pasta_killer
        edital["pasta_comprimidos"] = pasta_comprimidos
        
        edital_print = {k: v for k, v in edital.items() if k != "itens_dados" and  k != "itens_validos"}
        print(f"\nProcessando: {edital_print}\n")   
            
        if edital["Uf"].upper() == "RS":
            enviar_mensagem(edital, ids_usuarios)
            
        arquivos = buscar_arquivos(cnpj, ano, numero, link)
        if not arquivos:
            logs.info(f"[SEM ARQUIVOS API] {edital.get('Link')}")
        else:  
            salvar_arquivos_api(arquivos, edital, plataforma, cnpj, ano, numero)
        
        gravar_novo_processo(edital)
        return edital, 0
    
    except Exception as e:
        logs.error(f"[ERRO ao processar Edital:] {edital.get('Link', '').strip()} - {e}", exc_info=True)
        return None, error_timeout

def tentar_buscar_compra(cnpj, ano, numero, link, lista_erros_api, max_tentativas=3):   
    try:
        for tentativa in range(1, max_tentativas + 1):
            
            indice_erros_antes = len(lista_erros_api) if lista_erros_api is not None else 0
            
            compra, qtd_items, itens = buscar_compra_e_itens(cnpj, ano, numero, link, lista_erros_api=lista_erros_api)

            if isinstance(compra, dict):
                return compra, qtd_items, itens, False
            
            erro_foi_timeout = teve_timeout_get_json(lista_erros_api, indice_erros_antes)
            
            if not erro_foi_timeout:
                print(f"[ERRO API] Não é TIMEOUT_GET_JSON. Não vai tentar novamente: {link}")
                return None, None, None, False

            print(f"[TIMEOUT_GET_JSON] Tentativa {tentativa}/{max_tentativas} para o edital: {link}")

            if tentativa < max_tentativas:
                time.sleep(2)

        return None, None, None, True
    except Exception as ex:
        logs.error(f"[ERRO AO TENTAR BUSCAR COMPRA] {link} - {ex}", exc_info=True)
        return None, None, None, False
    
def tratar_timeout(edital, error_timeout, ids_usuarios):
    """Gerencia erros de timeout e decide se continua ou pausa processamento."""
   
    print("\n" + "="*94)
    print("ERRO NO SITE: MAIS DE 3 TIMEOUTS. AGUARDANDO 5 MINUTOS PARA TENTAR NOVAMENTE.")
    print("\n" + "="*94 + "\n")
    enviar_mensagem(edital, ids_usuarios, erro=True)
    
    time.sleep(300)
    
    return None, 0  


def extrair_link(texto, urlBase):
    id_aux = extrair_texto(texto, 'Id contratação PNCP: ')
    
    return {
        'Link': f"{urlBase.split('?')[0]}/{id_aux.split('-')[0]}/{id_aux.split('/')[-1]}/{id_aux.split('-')[2].split('/')[0].lstrip('0')}"
    }
    
def teve_timeout_get_json(lista_erros_api, indice_inicial):
    try:
        if lista_erros_api is None:
            return False

        erros_novos = lista_erros_api[indice_inicial:]

        return any(
            erro.get("tipo_erro") == "TIMEOUT_GET_JSON"
            for erro in erros_novos
        )
    except Exception as ex:
        logs.error(f"[ERRO AO VERIFICAR TIMEOUT_GET_JSON] {ex}")
        return False