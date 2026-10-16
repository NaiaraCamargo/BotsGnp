import re
from pncp_shared.utils.funcoespncp import *


CATALOGO = {

    1: [
        "nota adesiva", "notas adesivas",
        "post it", "postit",
        "bloco adesivo",
        "marcador adesivo",
        "folha adesiva"
    ],

    2: [
        "grampeador", "grampeadores",
        "grampo 26 6", "grampo 26/6", "grampo 26-6"
    ],

    3: [
        "perfurador", "perfuradores"
    ],

    4: [
        "corretivo",
        "caneta corretiva",
        "caneta corretivo",
        "liquid paper",
        "corretivo liquido",
        "corretivo branquinho"
    ],

    5: [
        "fita corretiva",
        "corretivo em fita",
        "fita para correcao",
        "corretivo roller",
        "corretivo seco"
    ],

    6: [
        "cola bastao",
        "tubo bastao",
        "cola isopor",
        "cola eva",
        "cola artesanato",
        "cola branca",
        "cola liquida",
        "cola lavavel",
        "cola atoxica",
        "cola polivinil acetato",
        "cola pva"
    ],

    7: [
        "pasta cartao",
        "cartao duplex",
        "pasta grampo trilho",
        "pasta oficio",
        "pasta aba elastico"
    ],

    8: [
        "clipes",
        "clip",
        "prendedor de papel"
    ],

    9: [
        "pasta suspensa",
        "pasta com haste",
        "pasta de haste",
        "pasta kraft",
        "pasta marmorizada"
    ],

    10: [
        "arquivo morto",
        "caixa box"
    ],

    11: [
        "registradores",
        "registradora",
        "pasta az",
        "registradora az",
        "az usual",
        "pasta lombo largo",
        "registrador lombo largo",
        "pasta lombo estreito",
        "registrador lombo estreito",
        "pasta memorando",
        "registrador memorando",
        "pasta duplicata",
        "registrador duplicata"
    ],

    12: [
        "bobina calculadora"
    ],

    13: [
        "bobina pdv",
        "bobina termica",
        "bobina pos",
        "bobina ecf",
        "bobina maquininha de cartao",
        "bobina cupom",
        "bobina cupom fiscal",
        "bobina rep",
        "bobina balanca"
    ],

    14: [
        "bobina relogio",
        "bobina de ponto"
    ],

    15: [
        "papel a4",
        "papel sulfite",
        "folha a4",
        "folha sulfite"
    ],

    16: [
        "papel a3",
        "folha a3"
    ],

    17: [
        "fita ribbon",
        "fita termica",
        "fita transferencia",
        "fita ttr"
    ]
}

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
            
            codigos = codigos_para_descricao(descricao)
            
            campos_itens.append({
                "numeroItem": numero,
                "descricaoItem": descricao,
                "quantidadeItem": quantidade,
                "valorUnitItem": valor_unit,
                "valorTotalItem": valor_total,
                "codigosCatalogo": codigos,
                "itemValidoCatalogo": bool(codigos)
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

def codigos_para_descricao(descricao: str) -> list[int]:
    t = normalizar(descricao)
    if not t:
        return []

    encontrados = set()
    for codigo, termos in CATALOGO.items():
        for termo in termos:
            termo_norm = normalizar(termo)
            if termo_bate(t, termo_norm):
                encontrados.add(codigo)
                break  # não repete dentro do mesmo código
    return sorted(encontrados)

def codigos_unicos_do_edital(itens_dados: list[dict]) -> list[int]:
    s = set()
    for it in (itens_dados or []):
        for c in (it.get("codigosCatalogo") or []):
            s.add(c)
    return sorted(s)
