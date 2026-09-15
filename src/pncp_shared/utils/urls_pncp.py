from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse
from pncp_shared.logs.controle_logs import logs


def definir_pagina_pncp(url_base, pagina):
    """Atualiza o parametro pagina independentemente da posicao dele na query string."""
    pagina = int(pagina)
    if pagina < 1:
        raise ValueError("A pagina deve ser maior que zero.")

    parsed = urlparse(str(url_base or ""))
    parametros, pagina_inserida = [], False

    for chave, valor in parse_qsl(parsed.query, keep_blank_values=True):
        if chave.lower() == "pagina":
            if not pagina_inserida:
                parametros.append(("pagina", str(pagina)))
                pagina_inserida = True
        else:
            parametros.append((chave, valor))

    if not pagina_inserida:
        parametros.append(("pagina", str(pagina)))

    return urlunparse(parsed._replace(query=urlencode(parametros, doseq=True)))


def aplicar_parametros_url(url_base, parametros_url):
    """Aplica/substitui parâmetros mantendo a URL cadastrada em pages."""
    parsed = urlparse(url_base)
    query_atual = parse_qs(parsed.query)
    query_adicional = parse_qs(str(parametros_url or "").lstrip("?&"))

    query_atual.update(query_adicional)
    query_atual["pagina"] = ["1"]

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query_atual, doseq=True),
        parsed.fragment,
    ))


def gerar_urls_variantes_pncp(url_base, termos_variantes):
    try:
        parsed = urlparse(url_base)
        query = parse_qs(parsed.query)

        termo_original = query.get("q", [""])[0].strip().lower()

        if not termo_original:
           return [{"url": url_base, "termo_busca": "sem_termo"}], "sem_termo"

        termos_unicos = {
            str(termo).strip().lower() for termo in (termos_variantes or [])
            if str(termo or "").strip()
        }
        termos_unicos.discard(termo_original)
        termos_ordenados = [termo_original, *sorted(termos_unicos)]

        urls = []

        for termo_variacao in termos_ordenados:
            nova_query = query.copy()
            nova_query["q"] = [termo_variacao]
            nova_query["pagina"] = ["1"]

            nova_query_string = urlencode(nova_query, doseq=True)

            nova_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                nova_query_string,
                parsed.fragment
            ))

            urls.append({
                "url": nova_url,
                "termo_busca": termo_variacao
            })

        return urls, termo_original
    except Exception as ex:
        logs.error(f"Erro ao gerar URLs variantes: {ex}")
        return [{"url": url_base, "termo_busca": termo_original or "sem_termo"}], termo_original or "sem_termo"
