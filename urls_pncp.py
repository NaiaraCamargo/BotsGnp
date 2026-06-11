from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from controle_logs import logs

def gerar_urls_variantes_pncp(url_base, termos_variantes):
    try:
        parsed = urlparse(url_base)
        query = parse_qs(parsed.query)

        termo_original = query.get("q", [""])[0].strip().lower()

        if not termo_original:
           return [{"url": url_base, "termo_busca": "sem_termo"}], "sem_termo"

        if not termos_variantes:
            termos_variantes = set()
        else:
            termos_variantes = set(termos_variantes)

        termos_variantes.add(termo_original)

        urls = []

        for termo_variacao in termos_variantes:
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