import re
import requests
from funcoespncp import *

CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP = "https://pncp.gov.br/pncp-api/v1"

def get_json(url, params=None, timeout=60, lista_erros_api=None, link_origem=None):
    try:
        headers = {
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

        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()

        try:
            return r.json()

        except ValueError as e:
            logs.error(f"[ERRO JSON] Resposta não é JSON válido - URL: {url}")

            adicionar_erro_url(lista_erros_api, url=url, params=params, tipo_erro="JSON_INVALIDO", mensagem=e, link_origem=link_origem)

            return None

    except requests.exceptions.Timeout as e:
        logs.error(f"[TIMEOUT get_json] URL: {url}")

        adicionar_erro_url(lista_erros_api, url=url, params=params, tipo_erro="TIMEOUT_GET_JSON", mensagem=e, link_origem=link_origem)

        return None

    except requests.exceptions.ConnectionError as e:
        logs.error(f"[ERRO CONEXÃO get_json] URL: {url}")

        adicionar_erro_url(lista_erros_api, url=url, params=params, tipo_erro="CONNECTION_ERROR_GET_JSON", mensagem=e, link_origem=link_origem)

        return None

    except requests.exceptions.HTTPError as e:
        logs.error(f"[ERRO HTTP get_json] {e} - URL: {url}")

        status_code = None

        try:
            status_code = e.response.status_code
        except Exception:
            pass

        tipo_erro = f"HTTP_ERROR_GET_JSON_{status_code}" if status_code else "HTTP_ERROR_GET_JSON"

        adicionar_erro_url(lista_erros_api, url=url, params=params, tipo_erro=tipo_erro, mensagem=e, link_origem=link_origem)

        return None

    except requests.exceptions.RequestException as e:
        logs.error(f"[ERRO REQUEST get_json] {e} - URL: {url}")

        adicionar_erro_url(lista_erros_api, url=url, params=params, tipo_erro="REQUEST_EXCEPTION_GET_JSON", mensagem=e, link_origem=link_origem)

        return None


def get_int(url, params=None, timeout=30, lista_erros_api=None, link_origem=None) -> int:
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    try:
        j = r.json()
        if isinstance(j, int):
            return j
        if isinstance(j, dict):
            for k in ("quantidade", "total", "value"):
                if k in j and isinstance(j[k], int):
                    return j[k]
        raise ValueError(f"Resposta inesperada: {j}")
    except ValueError as e:
        try:
            return int(r.text.strip())
        except Exception as e_text:
            logs.error(f"[ERRO PARSE TEXT GET INT] {e_text} - URL: {url}")
            return 0

def buscar_compra_e_itens(cnpj: str, ano: int, sequencial: int, link, timeout=30, lista_erros_api=None):
    try:
        compra_url = f"{CONSULTA}/orgaos/{cnpj}/compras/{ano}/{sequencial}"
        compra = get_json(compra_url, timeout=timeout, lista_erros_api=lista_erros_api, link_origem=link)

        if not isinstance(compra, dict):
            return None, 0, []

        qtd_url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/quantidade"
        qtd = get_int(qtd_url, timeout=timeout, lista_erros_api=lista_erros_api, link_origem=link)

        if not isinstance(qtd, int) or qtd <= 0:
            return compra, 0, []

        itens_url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
        itens_resp = get_json(itens_url, params={"pagina": 1, "tamanhoPagina": qtd}, timeout=timeout, lista_erros_api=lista_erros_api, link_origem=link)

        if isinstance(itens_resp, dict):
            itens = itens_resp.get("data") or []
        elif isinstance(itens_resp, list):
            itens = itens_resp
        else:
            itens = []

        return compra, qtd, itens

    except Exception as e:
        logs.error(f"[ERRO AO BUSCAR CAMPOS API] {link} - {e}", exc_info=True)
        return None, 0, []

def montar_novos_campos(compra: dict, qtd, link, palavras_destacadas):
    try:
        data_fim, hora_fim = separar_data_hora(
            compra.get("dataEncerramentoProposta")
        )
        
        descricao_tratada = destacar_palavras(
            limpar_para_mysql(compra.get("objetoCompra", "")),
            palavras_destacadas
        )
        
        novos_campos = {
            "Numero": f"{compra.get('numeroCompra')}/{compra.get('anoCompra')}",
            "NumeroAux": compra.get("numeroCompra") or None,
            "IdContratacaoPncp": compra.get("numeroControlePNCP"),
            "Licitacao": compra.get("modalidadeNome"),
            "Data": compra.get("dataPublicacaoPncp"),
            "Orgao": compra.get("orgaoEntidade", {}).get("razaoSocial", ""),
            "Municipio": compra.get("unidadeOrgao", {}).get("municipioNome", "")  + '/' + compra.get("unidadeOrgao", {}).get("ufSigla", "") ,
            "Uf": compra.get("unidadeOrgao", {}).get("ufSigla", ""),
            "Descricao": descricao_tratada,
            "Cnpj": compra.get("orgaoEntidade", {}).get("cnpj", ""),
            "DataInicioRecebimentoProposta": compra.get("dataAberturaProposta"),
            "CodigoUnidadeCompradora":  compra.get("unidadeOrgao", {}).get("codigoUnidade", ""),
            "ModoDeDisputa": compra.get("modoDisputaNome"),
            "Situacao": compra.get("situacaoCompraNome"),
            "DataFimRecebimentoProposta": compra.get("dataEncerramentoProposta"),
            "DataFim": data_fim,
            "HoraFim": hora_fim,
            "ValorTotalEstimadoCompra": formatar_valor_sigilo(compra.get("valorTotalEstimado")),
            "LinkBotao": compra.get("linkSistemaOrigem"), 
            "QuantidadeItens": qtd
        }
        
        return novos_campos
    except Exception as e:
        logs.error(f"[ERRO AO MONTAR CAMPOS API] {link} - {e}")

def montar_itens_campos(link: str, itens: list[dict]) -> list[dict]:
    try:
        campos_itens = []

        for item in (itens or []):
            numero = item.get("numeroItem")
            descricao = item.get("descricao")
            quantidade = item.get("quantidade")
            valor_unit = item.get("valorUnitarioEstimado") or item.get("valorUnitario")
            valor_total = item.get("valorTotalEstimado") or item.get("valorTotal")
            
            campos_itens.append({
                "numeroItem": numero,
                "descricaoItem": descricao,
                "quantidadeItem": quantidade,
                "valorUnitItem": valor_unit,
                "valorTotalItem": valor_total,
            })

        return campos_itens

    except Exception as e:
        logs.error(f"[ERRO AO MONTAR ITENS API] {link} - {e}")
        return []

def destacar_palavras(texto, palavras):
    if not palavras:
        return texto

    palavras_ordenadas = sorted(set(palavras), key=len, reverse=True)
    
    def substituir(match):
        return f"<b>{match.group(0)}</b>"

    for palavra in palavras_ordenadas:
        texto = re.sub(rf'\b{re.escape(palavra)}\b', substituir, texto, flags=re.IGNORECASE)

    return texto

def termo_bate(texto_norm: str, termo_norm: str) -> bool:
    # termo composto: exige todas as palavras presentes (qualquer ordem)
    partes = termo_norm.split()
    palavras_texto = set(texto_norm.split())
    return all(p in palavras_texto for p in partes)

def normalizar(txt: str) -> str:
    if not txt:
        return ""
    txt = txt.lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^a-z0-9\s]", " ", txt)   # tira pontuação
    txt = re.sub(r"\s+", " ", txt).strip()   # normaliza espaços
    return txt

def codigos_unicos_do_edital(itens_dados: list[dict]) -> list[int]:
    s = set()
    for it in (itens_dados or []):
        for c in (it.get("codigosCatalogo") or []):
            s.add(c)
    return sorted(s)

def adicionar_erro_url(lista_erros_api, url, params=None, tipo_erro=None, mensagem=None, link_origem=None):
    if lista_erros_api is None:
        return

    lista_erros_api.append({
        "url": url,
        "params": json.dumps(params, ensure_ascii=False) if params else None,
        "tipo_erro": tipo_erro,
        "mensagem": str(mensagem)[:4000] if mensagem else None,
        "link_origem": link_origem,
        "data_erro": datetime.now()
    })
