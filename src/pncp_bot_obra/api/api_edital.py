import re
from pncp_shared.utils.funcoespncp import *
from pncp_shared.logs.controle_logs import logs

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
            "Data": formatar_data_hora_string(compra.get("dataPublicacaoPncp", "")),
            "Orgao": compra.get("orgaoEntidade", {}).get("razaoSocial", ""),
            "Municipio": compra.get("unidadeOrgao", {}).get("municipioNome", "")  + '/' + compra.get("unidadeOrgao", {}).get("ufSigla", "") ,
            "Uf": compra.get("unidadeOrgao", {}).get("ufSigla", ""),
            "Descricao": descricao_tratada,
            "Cnpj": compra.get("orgaoEntidade", {}).get("cnpj", ""),
            "DataInicioRecebimentoProposta": formatar_data_hora_string(compra.get("dataAberturaProposta", "")),
            "CodigoUnidadeCompradora":  compra.get("unidadeOrgao", {}).get("codigoUnidade", ""),
            "ModoDeDisputa": compra.get("modoDisputaNome"),
            "Situacao": compra.get("situacaoCompraNome"),
            "DataFimRecebimentoProposta": formatar_data_hora_string(compra.get("dataEncerramentoProposta", "")),
            "DataFim": data_fim,
            "HoraFim": hora_fim,
            "ValorTotalEstimadoCompra": formatar_valor_sigilo(compra.get("valorTotalEstimado")),
            "LinkBotao": compra.get("linkSistemaOrigem"), 
            "FontesOrcamentarias": ", ".join(fonte["nome"] for fonte in (compra.get("fontesOrcamentarias") or []) if fonte.get("nome")),
            "fonte_plataforma": compra.get("usuarioNome") or "",
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
