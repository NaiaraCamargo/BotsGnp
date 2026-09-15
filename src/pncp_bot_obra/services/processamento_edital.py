from datetime import datetime
import time

from pncp_bot_obra.api.api_edital import (
    montar_novos_campos, 
    montar_itens_campos
)
from pncp_shared.api.compras_pncp import tentar_buscar_compra
from pncp_shared.api.api_arquivos import (
    buscar_arquivos, 
    salvar_arquivos_api
)
from pncp_shared.utils.funcoespncp import obter_pastas_download
from pncp_shared.database.repositoriopncp import (
    gravar_processo_botbool_envio, 
    verificar_existencia_edital_new, 
    gravar_novo_processo, 
    atualizar_termos_edital,
    bloquear_processamento_edital,
    retornar_destinos_enviados,
    retornar_destinos_processados,
    registrar_resultado_envio_bot,
)
from pncp_shared.utils.validadores_pncp import (
    validar_modalidade_obras,
    validar_palavras,
    validar_perfil_valid,
    extrair_chaves_do_link,
    extrair_texto,
)
from pncp_shared.logs.controle_logs import logs
from pncp_shared.controllers.controle_envio_TG import enviar_mensagem
from pncp_bot_obra.services.roteamento_bots import (
    calcular_destinos_aprovados,
    destinatarios_por_destino,
    normalizar_destinos,
)

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


def enviar_para_destinos(edital, id_processo, destinos, destinatarios):
    chats_ja_enviados = set()
    destinos_enviados = set()

    for destino in sorted(destinos):
        chats_destino = destinatarios_por_destino(destinatarios, destino)
        chats_novos = [chat for chat in chats_destino if chat not in chats_ja_enviados]

        if 'EDIT' in destino and edital["Uf"].upper() != "RS" and edital["Uf"].upper() != "SC":
            print(f"[IGNORADO - DESTINO EDIT DIFERENTE DE RS/SC] {destino} - {edital.get('Link')}")
            registrar_resultado_envio_bot(id_processo, destino, "ignorado", "Destino EDIT diferente de RS/SC ignorado")
            continue

        enviados_agora = enviar_mensagem(edital, chats_novos, destino=destino) if chats_novos else []

        chats_ja_enviados.update(str(chat) for chat in enviados_agora)
        destino_entregue = bool(set(chats_destino) & chats_ja_enviados)

        registrar_resultado_envio_bot(id_processo, destino, "enviado" if destino_entregue else "erro",
                                      "" if destino_entregue else "Nenhum destinatario do destino recebeu a mensagem")

        if destino_entregue:
            destinos_enviados.add(destino)

    return destinos_enviados

def processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, processar_dia, filtros_base, lock_editais, 
                    editais_em_processamento, error_timeout, lista_erros_api=None, termo_busca=None):

    if plataforma.startswith("obra") and not validar_modalidade_obras(texto):
        return None, error_timeout

    palavras_destacadas = validar_palavras(texto=texto, filtros_base=filtros_base)
    destinos_pagina = normalizar_destinos(filtros_base.get("banco", {}).get("destinos"))
    destinatarios = filtros_base.get("banco", {}).get("destinatarios", [])

    if not destinos_pagina:
        logs.error("[PAGINA SEM DESTINO] id_page=%s termo=%s", id_pagina, termo_busca)
        return None, error_timeout

    edital = extrair_link(texto, urlBase)
    link = edital.get("Link", "").strip()

    with lock_editais:
        if link in editais_em_processamento:
            print(f"[IGNORADO - EM PROCESSAMENTO] {link}")
            return None, error_timeout
        editais_em_processamento.add(link)

    try:
        palavras_limpa = [p.strip("'\"") for p in palavras_destacadas if p.strip("'\"")]

        edital.update({
            "palavras_chave": palavras_limpa if palavras_limpa else "",
            "termo_busca": termo_busca,
            "id_pagina": id_pagina,
            "notificar_retorno": True,
            "envio_notificacao": datetime.now()
        })

        with bloquear_processamento_edital(link) as lock_adquirido:
            if not lock_adquirido:
                logs.info(f"[IGNORADO - LOCK DE OUTRO EXECUTOR] {link}")
                return None, error_timeout

            edital_existente = verificar_existencia_edital_new(link)

            if edital_existente:
                termos_existentes = edital_existente.get("termos", "")

                if termo_ja_existe(termos_existentes, termo_busca):
                    destinos_processados = retornar_destinos_processados(edital_existente.get("id"))
                    if destinos_pagina.issubset(destinos_processados):
                        print(f"EDITAL COM TERMO JA PROCESSADO: {link}")
                        logs.info("Edital com termo ja processado: %s - %s - %s", edital_existente.get("id"), link, termo_busca)
                        return None, error_timeout
                else:
                    atualizar_termo_existente(edital_existente, termo_busca)

            edital, error_timeout = processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtros_base,
                                                     plataforma, lista_erros_api, destinos_pagina, destinatarios)

        return edital, error_timeout
    except Exception as e:
        logs.error(f"[ERRO AO PROCESSAR TEXTO] {link} - {e}", exc_info=True)
    finally:
        with lock_editais:
            editais_em_processamento.discard(link)

    return None, error_timeout


def processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtros_base, plataforma, lista_erros_api,destinos_pagina, destinatarios,):
    try:    
        link = edital["Link"]
        chaves = extrair_chaves_do_link(link)
        
        if not chaves:
            print(f"[LINK INVÁLIDO PNCP] {link}")
            logs.error(f"[LINK INVÁLIDO PNCP] {link}")
            return None, error_timeout

        cnpj, ano, numero = chaves
        
        compra, qtd_items, itens, falhou_por_timeout = tentar_buscar_compra(cnpj, ano, numero, link, lista_erros_api, max_tentativas=3)

        if compra is None:
            if falhou_por_timeout:
                return tratar_timeout(edital, error_timeout, destinos_pagina, destinatarios, tentativas=3)
            
            return None, error_timeout

        error_timeout = 0
           
        novos_dados = montar_novos_campos(compra, qtd_items, link, palavras_destacadas)
        
        itens_dados = montar_itens_campos(link, itens or [])
        edital["itens_dados"] = itens_dados
        
        palavra_chave_item = validar_palavras(itens=itens_dados, filtros_base=filtros_base)
        edit_valido = validar_perfil_valid(texto=compra.get("objetoCompra", ""), itens=itens_dados, filtros_base=filtros_base)
        codigo_executor = str(filtros_base.get("banco", {}).get("codigo_executor") or "").strip().upper()

        if codigo_executor == "EDIT" and not palavras_destacadas and not palavra_chave_item and not edit_valido:
            print(" NENHUMA PALAVRA CHAVE ENCONTRADA NO OBJETO E NOS ITENS\n")
            return None, error_timeout

        edital.update(novos_dados)

        destinos_aprovados = calcular_destinos_aprovados(edital, destinos_pagina, edit_valido=edit_valido)
        
        pasta_killer, pasta_comprimidos = obter_pastas_download(edital, plataforma)
        edital["pasta_download"] = pasta_killer
        edital["pasta_comprimidos"] = pasta_comprimidos
        
        edital_print = {k: v for k, v in edital.items() if k != "itens_dados" and  k != "itens_validos"}
        print(f"\nProcessando: {edital_print}\n")   
 
        arquivos = buscar_arquivos(cnpj, ano, numero, link)
        if not arquivos:
            logs.info(f"[SEM ARQUIVOS API] {edital.get('Link')}")
        else:  
            salvar_arquivos_api(arquivos, edital, plataforma, cnpj, ano, numero)
        
        id_processo = gravar_novo_processo(edital)

        if not id_processo:
            logs.error(f"[PROCESSO SEM ID] Nao foi possivel registrar os envios: {link}")
            return edital, 0

        destinos_ja_enviados = retornar_destinos_enviados(id_processo)
        destinos_pendentes = destinos_aprovados - destinos_ja_enviados

        for destino in destinos_pagina - destinos_aprovados - destinos_ja_enviados:
            registrar_resultado_envio_bot(id_processo, destino, "ignorado")

        destinos_enviados = enviar_para_destinos(edital, id_processo, destinos_pendentes, destinatarios)

        if "BOOL" in destinos_enviados:
            gravar_processo_botbool_envio(id_processo)
        
        return edital, 0
    
    except Exception as e:
        logs.error(f"[ERRO ao processar Edital:] {edital.get('Link', '').strip()} - {e}", exc_info=True)
        return None, error_timeout
    
def tratar_timeout(edital, error_timeout, destinos, destinatarios, tentativas=3):
    """Gerencia erros de timeout e decide se continua ou pausa processamento."""

    link = str(edital.get("Link") or "").strip()
    edital_alerta = dict(edital)
    edital_alerta.update({"tentativas_timeout": tentativas, "tempo_espera_minutos": 3})

    print("\n" + "="*94)
    print(f"ERRO NO SITE: LINK {link} FALHOU {tentativas} VEZES. AGUARDANDO 3 MINUTOS PARA NOVA TENTATIVA.")
    print("\n" + "="*94 + "\n")

    for destino in sorted(normalizar_destinos(destinos)):
        chats_destino = destinatarios_por_destino(destinatarios, destino)
        if chats_destino:
            enviar_mensagem(edital_alerta, chats_destino, erro=True, destino=destino)

    time.sleep(180)
    
    return None, 0  


def extrair_link(texto, urlBase):
    id_aux = extrair_texto(texto, 'Id contratação PNCP: ')
    
    return {
        'Link': f"{urlBase.split('?')[0]}/{id_aux.split('-')[0]}/{id_aux.split('/')[-1]}/{id_aux.split('-')[2].split('/')[0].lstrip('0')}"
    }
    
