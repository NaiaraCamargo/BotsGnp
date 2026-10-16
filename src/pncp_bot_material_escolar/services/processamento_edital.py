from datetime import datetime
import time

from pncp_shared.api.api_arquivos import buscar_arquivos, salvar_arquivos_api
from pncp_shared.api.compras_pncp import tentar_buscar_compra
from pncp_shared.utils.funcoespncp import obter_pastas_download
from pncp_shared.logs.controle_logs import logs
from pncp_shared.controllers.controle_envio_TG import enviar_mensagem
from pncp_shared.database.repositoriopncp import verificar_existencia_edital_new, gravar_novo_processo
from pncp_shared.utils.validadores_pncp import (
    validar_palavras,
    extrair_chaves_do_link,
    extrair_texto,
)
from pncp_bot_material_escolar.api.api_edital import (
    codigos_unicos_do_edital, 
    montar_novos_campos, 
    montar_itens_campos
)

def processar_texto(texto, plataforma, driver, urlBase, id_pagina, ids_usuarios, hora_atual, processar_dia, filtros_base, lock_editais, 
                    editais_em_processamento, error_timeout, lista_erros_api=None):
    
    palavras_destacadas = validar_palavras(texto=texto, filtros_base=filtros_base)

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

        resultado_existente = verificar_existencia_edital_new(edital["Link"])
        if resultado_existente:
            print(f"EDITAL JA EXISTE NO BANCO: {edital['Link']}\n")
            logs.info(f"Edital já existe no banco: {resultado_existente.get('id')} - {edital['Link']}\n")
            return None, error_timeout
        
        edital, error_timeout = processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtros_base, plataforma, lista_erros_api)

        return edital, error_timeout
    except Exception as e:
        logs.error(f"[ERRO AO PROCESSAR TEXTO] {link} - {e}", exc_info=True)
    finally:
        with lock_editais:
            editais_em_processamento.discard(link)

    return None, error_timeout

def processar_edital(edital, ids_usuarios, error_timeout, palavras_destacadas, filtros_base, plataforma, lista_erros_api):
    
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
            
        ##arquivos = buscar_arquivos(cnpj, ano, numero, link)
        ##if not arquivos:
            ##logs.info(f"[SEM ARQUIVOS API] {edital.get('Link')}")
        ##else:
            ##salvar_arquivos_api(arquivos, edital, plataforma, cnpj, ano, numero)
        
        gravar_novo_processo(edital)
        return edital, 0
    
    except Exception as e:
        logs.error(f"[ERRO ao processar Edital:] {edital.get('Link', '').strip()} - {e}", exc_info=True)
        return None, error_timeout

def tratar_timeout(edital, error_timeout, ids_usuarios):
    """Gerencia erros de timeout e decide se continua ou pausa processamento."""

    edital_alerta = dict(edital)
    edital_alerta.update({"tentativas_timeout": 3, "tempo_espera_minutos": 3})

    print("\n" + "="*94)
    print(f"ERRO NO SITE: LINK {edital.get('Link', '')} FALHOU 3 VEZES. AGUARDANDO 3 MINUTOS PARA NOVA TENTATIVA.")
    print("\n" + "="*94 + "\n")
    enviar_mensagem(edital_alerta, ids_usuarios, erro=True)
    
    time.sleep(180)
    
    return None, 0  


def extrair_link(texto, urlBase):
    id_aux = extrair_texto(texto, 'Id contratação PNCP: ')
    
    return {
        'Link': f"{urlBase.split('?')[0]}/{id_aux.split('-')[0]}/{id_aux.split('/')[-1]}/{id_aux.split('-')[2].split('/')[0].lstrip('0')}"
    }
