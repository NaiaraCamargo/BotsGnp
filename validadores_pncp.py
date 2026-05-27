import re
from unidecode import unidecode

def validar_modalidade_obras (texto):
    modalidade = extrair_texto(texto, 'Modalidade da Contratação: ')
    if modalidade not in ("Concorrência - Eletrônica", "Concorrência - Presencial", "Pregão - Eletrônico",
                            "Pregão - Presencial", "Dispensa", "Dispensa - Eletrônica"):
        return False
    else:
        return True
    
def validar_palavras(texto=None, itens=None, filtrosBase=None):
    encontradas = []
    palavras_chave_dict = filtrosBase.get("banco", {}).get("palavraschave", {})
    
    if not palavras_chave_dict:
        return []
    
    modo_itens = itens is not None and texto is None

    if texto is not None:
        pos_objeto = texto.lower().find("objeto:")
        if pos_objeto == -1:
            return []
        texto_original = texto[pos_objeto + len("objeto:"):].strip()
        text_list = [texto_original]

    elif itens is not None:
        text_list = [item.get("descricaoItem", "") for item in itens]
    else:
        return []

    for txt in text_list:
        texto_normalizado = unidecode(txt.lower())

        for palavra_chave, palavras_bloqueadas in palavras_chave_dict.items():
            chave_com_espacos = palavra_chave.replace("_", " ")
            chave_norm = unidecode(chave_com_espacos.lower())

            padrao = r"\b" + re.escape(chave_norm).replace(r"\ ", r"[\s\-]+") + r"\b"

            if not re.search(padrao, texto_normalizado):
                continue

            if any(re.search(rf"\b{re.escape(unidecode(pb.lower()))}\b", texto_normalizado)
                   for pb in palavras_bloqueadas):
                continue
            
            encontradas.append(chave_com_espacos)
            
            if modo_itens:
                return encontradas

    return encontradas

def extrair_chaves_do_link(link: str):
    m = re.search(r"/app/editais/(\d{14})/(\d{4})/(\d+)", link)
    if not m:
        return None
    cnpj, ano, numero = m.group(1), int(m.group(2)), int(m.group(3))
    return cnpj, ano, numero


def extrair_texto(texto, chave):
    """Extrai o valor associado a uma chave no texto."""
    try:
        return texto.split(chave)[1].split('\n')[0].strip().replace("'", "")
    except IndexError:
        return None