import json
from datetime import datetime

import requests

from pncp_shared.api.cliente_pncp import requisicao_pncp
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


def buscar_compra_e_itens(cnpj, ano, sequencial, link, timeout=60, lista_erros_api=None, max_tentativas=3):
    try:
        compra_url = f"{CONSULTA}/orgaos/{cnpj}/compras/{ano}/{sequencial}"
        compra = get_json(
            compra_url,
            timeout=timeout,
            lista_erros_api=lista_erros_api,
            link_origem=link, max_tentativas=max_tentativas,
        )

        if not isinstance(compra, dict):
            return None, 0, []

        qtd_url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/quantidade"
        indice_erros_qtd = len(lista_erros_api) if lista_erros_api is not None else 0
        qtd = get_int(qtd_url, timeout=timeout, lista_erros_api=lista_erros_api, link_origem=link, max_tentativas=max_tentativas)

        if lista_erros_api is not None and len(lista_erros_api) > indice_erros_qtd:
            return None, 0, []

        if not isinstance(qtd, int) or qtd <= 0:
            return compra, 0, []

        itens_url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
        itens = []
        total_paginas = (qtd + TAMANHO_PAGINA_ITENS - 1) // TAMANHO_PAGINA_ITENS

        for pagina in range(1, total_paginas + 1):
            itens_resposta = get_json(
                itens_url,
                params={"pagina": pagina, "tamanhoPagina": TAMANHO_PAGINA_ITENS},
                timeout=timeout,
                lista_erros_api=lista_erros_api,
                link_origem=link, max_tentativas=max_tentativas,
            )

            if isinstance(itens_resposta, dict):
                itens_pagina = itens_resposta.get("data") or []
            elif isinstance(itens_resposta, list):
                itens_pagina = itens_resposta
            else:
                return None, 0, []

            itens.extend(itens_pagina)
            if len(itens_pagina) < TAMANHO_PAGINA_ITENS:
                break

        return compra, qtd, itens

    except Exception as erro:
        logs.error(f"[ERRO AO BUSCAR CAMPOS API] {link} - {erro}", exc_info=True)
        return None, 0, []


def tentar_buscar_compra(cnpj, ano, numero, link, lista_erros_api, max_tentativas=3):
    indice_erros_antes = len(lista_erros_api) if lista_erros_api is not None else 0
    compra, qtd_items, itens = buscar_compra_e_itens(cnpj, ano, numero, link, lista_erros_api=lista_erros_api, max_tentativas=max_tentativas)

    if isinstance(compra, dict):
        return compra, qtd_items, itens, False

    falhou_apos_retentar = houve_erro_retentavel(lista_erros_api, indice_erros_antes)
    print(f"[ERRO API] {max_tentativas} tentativas esgotadas para o edital: {link}" if falhou_apos_retentar else f"[ERRO API] Erro não permite nova tentativa: {link}")
    return None, None, None, falhou_apos_retentar
