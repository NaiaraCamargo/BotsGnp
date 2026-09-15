from datetime import datetime
from threading import Lock
import time

from pncp_shared.api.api_arquivos import buscar_arquivos, salvar_arquivos_api
from pncp_shared.api.compras_pncp import tentar_buscar_compra
from pncp_shared.utils.funcoespncp import obter_pastas_download
from pncp_shared.logs.controle_logs import logs
from pncp_shared.controllers.controle_envio_TG import enviar_mensagem
from pncp_shared.database.repositoriopncp import (
    verificar_existencia_edital_new,
    gravar_novo_processo,
    retornar_destinatarios_filtros_seguro,
    registrar_notificacoes_busca,
)
from pncp_shared.utils.validadores_pncp import (
    validar_texto_seguro,
    extrair_chaves_do_link,
    extrair_texto,
)
from pncp_bot_seguro.api.api_edital import (
    montar_novos_campos, 
    montar_itens_campos
)

INTERVALO_ALERTA_TIMEOUT_SEG = 180
_lock_alertas_timeout = Lock()
_ultimos_alertas_timeout = {}

def processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, processar_dia, filtros_base, lock_editais, 
                    editais_em_processamento, error_timeout, lista_erros_api=None, id_busca=None):
    
    palavras_destacadas = validar_texto_seguro(texto, filtros_base)
    
    if not palavras_destacadas:
        print("NENHUMA PALAVRA CHAVE ENCONTRADA")
        return None, error_timeout

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

        edital.update({"id_pagina": id_pagina, "notificar_retorno": True,
                       "envio_notificacao": datetime.now()})

        resultado_existente = verificar_existencia_edital_new(edital["Link"])
        id_processo_existente = resultado_existente.get("id") if resultado_existente else None
        destinatarios_filtro = []
        ids_envio = ids_usuarios

        if id_busca is None and resultado_existente:
            print(f"EDITAL JA EXISTE NO BANCO: {edital['Link']}\n")
            logs.info(f"Edital já existe no banco: {id_processo_existente} - {edital['Link']}\n")
            return None, error_timeout

        if id_busca is not None:
            destinatarios_filtro = retornar_destinatarios_filtros_seguro(id_busca, id_processo=id_processo_existente)
            ids_envio = [item["id_telegram"] for item in destinatarios_filtro]

            if not ids_envio:
                logs.info(f"Nenhum destinatário pendente para busca={id_busca}, "
                          f"processo={id_processo_existente or 'novo'}, link={edital['Link']}")
                return None, error_timeout

        edital, error_timeout = processar_edital(edital, ids_envio, error_timeout, palavras_destacadas, filtros_base, plataforma,
            lista_erros_api, id_busca, id_processo_existente, destinatarios_filtro)

        return edital, error_timeout
    except Exception as e:
        logs.error(f"[ERRO AO PROCESSAR TEXTO] {link} - {e}")
    finally:
        with lock_editais:
            editais_em_processamento.discard(link)

    return None, error_timeout

def processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtros_base, plataforma, lista_erros_api,
                    id_busca=None, id_processo_existente=None, destinatarios_filtro=None):
    
    try:    
        link = edital["Link"]
        chaves = extrair_chaves_do_link(link)
        
        if not chaves:
            print(f"[LINK INVÁLIDO PNCP] {link} \n")
            logs.error(f"[LINK INVÁLIDO PNCP] {link}\n")
            return None, error_timeout

        cnpj, ano, numero = chaves
        
        compra, qtd_items, itens, falhou_por_timeout  = tentar_buscar_compra(cnpj, ano, numero, link, lista_erros_api)

        if compra is None:
            if falhou_por_timeout:
                return tratar_timeout(edital, error_timeout, ids_usuarios)
            
            return None, error_timeout

        error_timeout = 0
        
        novos_dados = montar_novos_campos(compra, qtd_items, link, palavras_destacadas)
        
        itens_dados = montar_itens_campos(link, itens or [])
        edital["itens_dados"] = itens_dados
        edital.update(novos_dados)
        
        pasta_killer, pasta_comprimidos = obter_pastas_download(edital, plataforma)
        edital["pasta_download"] = pasta_killer
        edital["pasta_comprimidos"] = pasta_comprimidos
        
        edital_print = {k: v for k, v in edital.items() if k != "itens_dados" and  k != "itens_validos"}
        print(f"\nProcessando: {edital_print}\n")
        
        chats_enviados = []

        if id_busca is not None:
            chats_enviados = enviar_mensagem(edital, ids_usuarios)

        if id_busca is not None and id_processo_existente:
            registrar_notificacoes_busca(id_processo_existente, id_busca, destinatarios_filtro, chats_enviados)
            return edital, 0

        elif id_busca is None:
            enviar_mensagem(edital, ids_usuarios)
            
        arquivos = buscar_arquivos(cnpj, ano, numero, link)
        if not arquivos:
            logs.info(f"[SEM ARQUIVOS API] {edital.get('Link')}")
        else:  
            salvar_arquivos_api(arquivos, edital, plataforma, cnpj, ano, numero)
        
        id_processo = gravar_novo_processo(edital, plataforma)

        if id_busca is not None and id_processo:
            registrar_notificacoes_busca(id_processo, id_busca, destinatarios_filtro, chats_enviados)

        return edital, 0
    
    except Exception as e:
        logs.error(f"[ERRO ao processar Edital:] {edital.get('Link', '').strip()} - {e}", exc_info=True)
        return None, error_timeout

def obter_palavra_chave_timeout(edital):
    palavras = edital.get("palavras_chave")

    if isinstance(palavras, list):
        palavras = ", ".join(str(p).strip() for p in palavras if str(p).strip())

    palavras = str(palavras or "").strip()

    return palavras or "sem_palavra_chave"


def deve_enviar_alerta_timeout(palavra_chave, intervalo_seg=INTERVALO_ALERTA_TIMEOUT_SEG):
    agora = time.monotonic()

    with _lock_alertas_timeout:
        ultimo_alerta = _ultimos_alertas_timeout.get(palavra_chave)

        if ultimo_alerta and agora - ultimo_alerta < intervalo_seg:
            return False, int(intervalo_seg - (agora - ultimo_alerta))

        _ultimos_alertas_timeout[palavra_chave] = agora
        return True, 0


def tratar_timeout(edital, error_timeout, ids_usuarios):
    """Gerencia erros de timeout e decide se continua ou pausa processamento."""
    palavra_chave = obter_palavra_chave_timeout(edital)
    enviar_alerta, segundos_restantes = deve_enviar_alerta_timeout(palavra_chave)
   
    print("\n" + "="*94)
    print(f"ERRO NO SITE: TIMEOUT NA PALAVRA-CHAVE '{palavra_chave}'. AGUARDANDO 3 MINUTOS PARA TENTAR NOVAMENTE.")
    print("\n" + "="*94 + "\n")

    if enviar_alerta:
        edital_alerta = dict(edital)
        edital_alerta.update({"palavra_chave_timeout": palavra_chave, "tentativas_timeout": 3, "tempo_espera_minutos": 3})
        enviar_mensagem(edital_alerta, ids_usuarios, erro=True)
    else:
        logs.warning(
            f"[TIMEOUT] Alerta suprimido para palavra-chave '{palavra_chave}'. "
            f"Novo alerta permitido em {segundos_restantes}s."
        )
    
    time.sleep(180)
    
    return None, 0  


def extrair_link(texto, urlBase):
    id_aux = extrair_texto(texto, 'Id contratação PNCP: ')
    
    return {
        'Link': f"{urlBase.split('?')[0]}/{id_aux.split('-')[0]}/{id_aux.split('/')[-1]}/{id_aux.split('-')[2].split('/')[0].lstrip('0')}"
    }
