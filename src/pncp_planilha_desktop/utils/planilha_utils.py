import re


def plataforma_tem_itens(plataforma):
    return plataforma.lower() != "seguro"


def format_data(data):
    partes = data.split("-")
    return partes[2] + "-" + partes[1] + "-" + partes[0]


def limpar_nome_arquivo(nome):
    nome = re.sub(r'[\\/:*?"<>|]', '_', nome).strip()
    return nome or "arquivo"
