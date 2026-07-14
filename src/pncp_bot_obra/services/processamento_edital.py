from datetime import datetime
import time

from pncp_bot_obra.api.api_edital import (
    buscar_compra_e_itens,
    montar_novos_campos, 
    montar_itens_campos
)
from pncp_shared.api.api_arquivos import (
    buscar_arquivos, 
    salvar_arquivos_api
)
from pncp_shared.utils.funcoespncp import (
    converter_moeda_brl_para_float, 
    obter_pastas_download
)
from pncp_shared.database.repositoriopncp import (
    gravar_processo_botbool_envio, 
    verificar_existencia_edital_new, 
    gravar_novo_processo, 
    atualizar_termos_edital
)
from pncp_shared.utils.validadores_pncp import (
    validar_modalidade_obras,
    validar_palavras,
    extrair_chaves_do_link,
    extrair_texto,
)
from pncp_shared.logs.controle_logs import logs
from pncp_shared.controllers.controle_envio_TG import enviar_mensagem

def obter_flags_envio(filtros_base, edital_existente=None):
    try:
        filter_atual = filtros_base.get("banco", {}).get("filter")
        filter_existente = edital_existente.get("filter") if edital_existente else None

        mapa_filters = {
            "ALL": {"ALL", "GNP", "BOOL"},
            "GNP": {"GNP"},
            "BOOL": {"BOOL"}
        }

        filtros_atuais = mapa_filters.get(filter_atual, set())
        filtros_existentes = mapa_filters.get(filter_existente, set())

        filtros_para_enviar = filtros_atuais - filtros_existentes

        return {
            "all": "ALL" in filtros_para_enviar,
            "gnp": "GNP" in filtros_para_enviar,
            "bool": "BOOL" in filtros_para_enviar
        }
    except Exception as e:
        logs.error(f"[ERRO AO OBTER FLAGS DE ENVIO] {e}")

def termo_ja_existe(termos_existentes, termo_busca):
    if not termo_busca:
        return False

    termos = [
        termo.strip().lower()
        for termo in (termos_existentes or "").split(";")
        if termo.strip()
    ]

    return termo_busca.strip().lower() in termos


def atualizar_termo_existente(edital_existente, termo_busca):
    if not termo_busca:
        return

    termos_existentes = edital_existente.get("termos", "") or ""

    novos_termos = (
        f"{termos_existentes}; {termo_busca}"
        if termos_existentes
        else termo_busca
    )

    atualizar_termos_edital(edital_existente["id"], novos_termos)


def definir_envio_bots(edital, flags_envio):
    bot_gnp = False
    bot_bool = False

    uf = str(edital.get("Uf", "")).upper()
    valor_total = str(edital.get("ValorTotalEstimadoCompra", "")).strip().upper()

    valor_estimado = (
        0
        if valor_total == "SIGILOSO"
        else converter_moeda_brl_para_float(valor_total)
    )

    if uf in ["RS", "SC"] and (flags_envio["all"] or flags_envio["gnp"]):
        bot_gnp = True

    if valor_estimado > 500000 or (
        valor_total == "SIGILOSO" and (flags_envio["all"] or flags_envio["bool"])
    ):
        bot_bool = True

    return bot_gnp, bot_bool

def processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, processar_dia, filtros_base, lock_editais, 
                    editais_em_processamento, error_timeout, lista_erros_api=None, termo_busca=None):
    
    if plataforma.startswith("obra") and not validar_modalidade_obras(texto):
        return None, error_timeout
    
    palavras_destacadas = validar_palavras(texto=texto, filtros_base=filtros_base)

    edital = extrair_link(texto, urlBase)
    link = edital.get("Link", "").strip()

    with lock_editais:
        if link in editais_em_processamento:
            print(f"[IGNORADO - EM PROCESSAMENTO] {link}")
            return None, error_timeout
        editais_em_processamento.add(link)

    try:
        #if processar_dia and 5 <= hora_atual < 9:
            #if datetime.strptime(edital["Data"], "%d/%m/%Y").date() != datetime.today().date():
                #return None, error_timeout

        palavras_limpa = [p.strip("'\"") for p in palavras_destacadas if p.strip("'\"")]
        
        edital.update({
            "palavras_chave": palavras_limpa if palavras_limpa else "",
            "termo_busca": termo_busca,
            "id_pagina": id_pagina,
            "notificar_retorno": True,
            "envio_notificacao": datetime.now()
        })
        
        flags_envio = {
            "all": False,
            "gnp": False,
            "bool": False
        }

        edital_existente = verificar_existencia_edital_new(link)
        
        if edital_existente:
            termos_existentes = edital_existente.get("termos", "")

            if termo_ja_existe(termos_existentes, termo_busca):
                print(f"EDITAL COM TERMO JÁ EXISTE NO BANCO: {link}")
                logs.info(
                    f"Edital com termo já existe no banco: "
                    f"{edital_existente.get('id')} - {edital.get('Link')} - {termo_busca}"
                )
                return None, error_timeout

            atualizar_termo_existente(edital_existente, termo_busca)
        
        flags_envio = obter_flags_envio(filtros_base, edital_existente)
                
        edital, error_timeout = processar_edital(
            edital=edital,
            ids_usuarios=ids_usuarios,
            error_timeout=error_timeout,
            palavras_destacadas=palavras_destacadas,
            filtros_base=filtros_base,
            plataforma=plataforma,
            lista_erros_api=lista_erros_api,
            flags_envio=flags_envio
        )

        return edital, error_timeout
    except Exception as e:
        logs.error(f"[ERRO AO PROCESSAR TEXTO] {link} - {e}")
    finally:
        with lock_editais:
            editais_em_processamento.discard(link)

    return None, error_timeout

def processar_edital(
    edital, ids_usuarios, error_timeout, palavras_destacadas,
    filtros_base, plataforma, lista_erros_api, flags_envio
):
    try:    
        link = edital["Link"]
        chaves = extrair_chaves_do_link(link)
        
        if not chaves:
            print(f"[LINK INVÁLIDO PNCP] {link}")
            logs.error(f"[LINK INVÁLIDO PNCP] {link}")
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
        
        palavra_chave_item = validar_palavras(itens=itens_dados, filtros_base=filtros_base)
        
        #if not palavras_destacadas and not palavra_chave_item:
           # print(" NENHUMA PALAVRA CHAVE ENCONTRADA NO OBJETO E NOS ITENS\n")
            #return None, error_timeout

        edital.update(novos_dados)
        
        pasta_killer, pasta_comprimidos = obter_pastas_download(edital, plataforma)
        edital["pasta_download"] = pasta_killer
        edital["pasta_comprimidos"] = pasta_comprimidos
        
        edital_print = {k: v for k, v in edital.items() if k != "itens_dados" and  k != "itens_validos"}
        print(f"\nProcessando: {edital_print}\n")   
 
        bot_gnp, bot_bool = definir_envio_bots(edital, flags_envio)
        
        if bot_gnp or bot_bool:
            enviar_mensagem(edital, ids_usuarios, bot_gnp, bot_bool)
            
        arquivos = buscar_arquivos(cnpj, ano, numero, link)
        if not arquivos:
            logs.info(f"[SEM ARQUIVOS API] {edital.get('Link')}")
        else:  
            salvar_arquivos_api(arquivos, edital, plataforma, cnpj, ano, numero)
        
        id_processo = gravar_novo_processo(edital)
        
        if bot_bool and id_processo:
            gravar_processo_botbool_envio(id_processo)
        
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
            
            erro_permite_nova_tentativa = deve_tentar_novamente_api(lista_erros_api, indice_erros_antes)
            
            if not erro_permite_nova_tentativa:
                print(f"[ERRO API] Erro não permite nova tentativa. Pulando edital: {link}")
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
    
def deve_tentar_novamente_api(lista_erros_api, indice_inicial):
    try:
        if lista_erros_api is None:
            return False

        erros_novos = lista_erros_api[indice_inicial:]

        tipos_retry = {
            "TIMEOUT_GET_JSON",
            "HTTP_ERROR_GET_JSON_429",
            "HTTP_ERROR_GET_JSON_500",
            "HTTP_ERROR_GET_JSON_502",
            "HTTP_ERROR_GET_JSON_503",
            "HTTP_ERROR_GET_JSON_504",
        }

        return any(
            erro.get("tipo_erro") in tipos_retry
            for erro in erros_novos
        )
        
    except Exception as ex:
        logs.error(f"[ERRO AO VERIFICAR TIMEOUT_GET_JSON] {ex}")
        return False
  