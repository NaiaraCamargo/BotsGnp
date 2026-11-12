import re
import unicodedata


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

def classificar_itens_catalogo(itens_dados: list[dict]) -> list[dict]:
    classificados = []
    for item in itens_dados or []:
        codigos = codigos_para_descricao(item.get("descricaoItem"))
        classificados.append({**item, "codigosCatalogo": codigos, "itemValidoCatalogo": bool(codigos)})
    return classificados


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
