import json
from datetime import datetime

import requests

from pncp_shared.api.cliente_pncp import requisicao_pncp
from pncp_shared.api.api_edital import montar_complementos_compra
from pncp_shared.logs.controle_logs import logs


CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP = "https://pncp.gov.br/pncp-api/v1"
TAMANHO_PAGINA_ITENS = 20
TIPOS_ERRO_RETENTAVEL = frozenset({"TIMEOUT_GET_JSON", "CONNECTION_ERROR_GET_JSON", "HTTP_ERROR_GET_JSON_429",
                                   "HTTP_ERROR_GET_JSON_500", "HTTP_ERROR_GET_JSON_502", "HTTP_ERROR_GET_JSON_503",
                                   "HTTP_ERROR_GET_JSON_504"})

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://pncp.gov.br/app/editais",
    "Origin": "https://pncp.gov.br",
    "Connection": "keep-alive",
}


def adicionar_erro_url(lista_erros_api, url, params=None, tipo_erro=None,
                       mensagem=None, link_origem=None):
    if lista_erros_api is None:
        return

    lista_erros_api.append({
        "url": url,
        "params": json.dumps(params, ensure_ascii=False) if params else None,
        "tipo_erro": tipo_erro,
        "mensagem": str(mensagem)[:4000] if mensagem else None,
        "link_origem": link_origem,
        "data_erro": datetime.now(),
    })


def houve_erro_retentavel(lista_erros_api, indice_inicial):
    erros_novos = (lista_erros_api or [])[indice_inicial:]
    return any(erro.get("tipo_erro") in TIPOS_ERRO_RETENTAVEL for erro in erros_novos)


def get_json(url, params=None, timeout=60, lista_erros_api=None, link_origem=None, max_tentativas=3):
    try:
        response = requisicao_pncp("GET", url, params=params, headers=HEADERS, timeout=timeout, max_tentativas=max_tentativas)
        response.raise_for_status()

        try:
            return response.json()
        except ValueError as erro:
            logs.error(f"[ERRO JSON] Resposta não é JSON válido - URL: {url}")
            adicionar_erro_url(
                lista_erros_api, url, params, "JSON_INVALIDO", erro, link_origem
            )

    except requests.exceptions.Timeout as erro:
        logs.error(f"[TIMEOUT get_json] URL: {url}")
        adicionar_erro_url(
            lista_erros_api, url, params, "TIMEOUT_GET_JSON", erro, link_origem
        )

    except requests.exceptions.ConnectionError as erro:
        logs.error(f"[ERRO CONEXÃO get_json] URL: {url}")
        adicionar_erro_url(
            lista_erros_api, url, params, "CONNECTION_ERROR_GET_JSON", erro,
            link_origem
        )

    except requests.exceptions.HTTPError as erro:
        status = getattr(erro.response, "status_code", None)
        tipo = f"HTTP_ERROR_GET_JSON_{status}" if status else "HTTP_ERROR_GET_JSON"
        logs.error(f"[ERRO HTTP get_json] {erro} - URL: {url}")
        adicionar_erro_url(
            lista_erros_api, url, params, tipo, erro, link_origem
        )

    except requests.exceptions.RequestException as erro:
        logs.error(f"[ERRO REQUEST get_json] {erro} - URL: {url}")
        adicionar_erro_url(
            lista_erros_api, url, params, "REQUEST_EXCEPTION_GET_JSON", erro,
            link_origem
        )

    return None


def get_int(url, params=None, timeout=60, lista_erros_api=None, link_origem=None, max_tentativas=3):
    try:
        response = requisicao_pncp("GET", url, params=params, timeout=timeout, max_tentativas=max_tentativas)
        response.raise_for_status()

        try:
            resultado = response.json()
            if isinstance(resultado, int):
                return resultado
            if isinstance(resultado, dict):
                for chave in ("quantidade", "total", "value"):
                    if isinstance(resultado.get(chave), int):
                        return resultado[chave]
        except ValueError:
            pass

        return int(response.text.strip())
    except requests.exceptions.Timeout as erro:
        logs.error(f"[TIMEOUT get_int] URL: {url}")
        adicionar_erro_url(lista_erros_api, url, params, "TIMEOUT_GET_JSON", erro, link_origem)
    except requests.exceptions.ConnectionError as erro:
        logs.error(f"[ERRO CONEXÃO get_int] URL: {url}")
        adicionar_erro_url(lista_erros_api, url, params, "CONNECTION_ERROR_GET_JSON", erro, link_origem)
    except requests.exceptions.HTTPError as erro:
        status = getattr(erro.response, "status_code", None)
        tipo = f"HTTP_ERROR_GET_JSON_{status}" if status else "HTTP_ERROR_GET_JSON"
        logs.error(f"[ERRO HTTP get_int] {erro} - URL: {url}")
        adicionar_erro_url(lista_erros_api, url, params, tipo, erro, link_origem)
    except (requests.exceptions.RequestException, TypeError, ValueError) as erro:
        logs.error(f"[ERRO get_int] {erro} - URL: {url}")
        adicionar_erro_url(lista_erros_api, url, params, "REQUEST_EXCEPTION_GET_JSON", erro, link_origem)

    return 0


def complementar_edital(edital, cnpj, ano, sequencial, lista_erros_api=None, timeout=60, max_tentativas=3):
    """Falhas da consulta sao registradas e nao impedem a gravacao do edital com seus itens."""
    url = f'{CONSULTA}/orgaos/{cnpj}/compras/{ano}/{sequencial}'
    erros = lista_erros_api if lista_erros_api is not None else []
    indice_inicial = len(erros)
    try:
        compra = get_json(url, timeout=timeout, lista_erros_api=erros, link_origem=edital['Link'], max_tentativas=max_tentativas)
        if compra is None and len(erros) > indice_inicial:
            return edital
        if not isinstance(compra, dict) or not compra:
            raise ValueError('Resposta da consulta de compra invalida ou vazia.')
        edital.update(montar_complementos_compra(compra, edital))
    except Exception as erro:
        logs.error('[ERRO AO COMPLEMENTAR EDITAL API] %s - %s', edital.get('Link'), erro, exc_info=True)
        adicionar_erro_url(erros, url, tipo_erro='COMPLEMENTOS_EDITAL_INVALIDOS', mensagem=erro, link_origem=edital.get('Link'))
    return edital


def buscar_itens(cnpj, ano, sequencial, link, timeout=60, lista_erros_api=None, max_tentativas=3):
    erros = lista_erros_api if lista_erros_api is not None else []
    itens_url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
    try:
        indice_inicial = len(erros)
        qtd = get_int(f"{itens_url}/quantidade", timeout=timeout, lista_erros_api=erros, link_origem=link, max_tentativas=max_tentativas)
        if len(erros) > indice_inicial:
            return None, []
        if not isinstance(qtd, int) or isinstance(qtd, bool) or qtd < 0:
            raise ValueError('Quantidade de itens invalida.')
        itens = []
        for pagina in range(1, (qtd + TAMANHO_PAGINA_ITENS - 1) // TAMANHO_PAGINA_ITENS + 1):
            resposta = get_json(itens_url, params={'pagina': pagina, 'tamanhoPagina': TAMANHO_PAGINA_ITENS},
                                timeout=timeout, lista_erros_api=erros, link_origem=link, max_tentativas=max_tentativas)
            if resposta is None and len(erros) > indice_inicial:
                return None, []
            itens_pagina = resposta.get('data') if isinstance(resposta, dict) else resposta
            if not isinstance(itens_pagina, list) or not all(isinstance(item, dict) for item in itens_pagina):
                raise ValueError(f'Resposta de itens invalida na pagina {pagina}.')
            itens.extend(itens_pagina)
        if len(itens) != qtd:
            raise ValueError(f'Itens incompletos: esperado={qtd}, recebido={len(itens)}.')
        numeros = [item.get('numeroItem') for item in itens]
        if any(numero is None for numero in numeros) or len(set(numeros)) != qtd:
            raise ValueError('Itens sem identificador ou duplicados na paginacao.')
        return qtd, itens
    except Exception as erro:
        logs.error(f'[ERRO AO BUSCAR ITENS API] {link} - {erro}', exc_info=True)
        adicionar_erro_url(erros, itens_url, tipo_erro='ITENS_INCOMPLETOS', mensagem=erro, link_origem=link)
        return None, []


def tentar_buscar_itens(cnpj, ano, numero, link, lista_erros_api, max_tentativas=3):
    erros = lista_erros_api if lista_erros_api is not None else []
    indice_inicial = len(erros)
    quantidade, itens = buscar_itens(cnpj, ano, numero, link, lista_erros_api=erros, max_tentativas=max_tentativas)
    return quantidade, itens, quantidade is None and houve_erro_retentavel(erros, indice_inicial)
