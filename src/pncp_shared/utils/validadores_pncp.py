import re
import string
from unidecode import unidecode
from pncp_shared.logs.controle_logs import logs


def _listas_regra(regra):
    if isinstance(regra, dict):
        return regra.get("exceptions", []) or [], regra.get("valid", []) or []
    return regra or [], []


def _normalizar_texto_busca(valor):
    texto = unidecode(str(valor or "").lower())
    texto = re.sub(r"[^a-z0-9\s-]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _contem_expressao(texto_normalizado, expressao):
    expressao_normalizada = _normalizar_texto_busca(expressao)
    if not expressao_normalizada:
        return False
    padrao = r"\b" + re.escape(expressao_normalizada).replace(r"\ ", r"[\s\-]+") + r"\b"
    return bool(re.search(padrao, texto_normalizado))


def _encontrar_valids(textos, regras):
    encontradas = []

    for texto in textos:
        texto_normalizado = _normalizar_texto_busca(texto)

        for regra in regras.values():
            palavras_bloqueadas, valid = _listas_regra(regra)
            if any(_contem_expressao(texto_normalizado, bloqueada) for bloqueada in palavras_bloqueadas):
                continue

            for expressao in valid:
                if _contem_expressao(texto_normalizado, expressao) and expressao not in encontradas:
                    encontradas.append(expressao)

    return encontradas


def validar_perfil_valid(texto=None, itens=None, filtros_base=None):
    """Retorna True quando alguma expressao valid do perfil aparece no objeto/itens."""
    regras = (filtros_base or {}).get("banco", {}).get("palavraschave", {})
    textos = ([texto] if texto else []) + [item.get("descricaoItem", "") for item in (itens or [])]
    return bool(_encontrar_valids(textos, regras))

def validar_modalidade_obras (texto):
    modalidade = extrair_texto(texto, 'Modalidade de Contratação: ')
    if modalidade not in ("Concorrência - Eletrônica", "Concorrência - Presencial", "Pregão - Eletrônico",
                            "Pregão - Presencial", "Dispensa", "Dispensa - Eletrônica"):
        return False
    else:
        return True
    
def validar_palavras(texto=None, itens=None, filtros_base=None):
    try:   
        encontradas = []
        palavras_chave_dict = filtros_base.get("banco", {}).get("palavraschave", {})
        
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
            texto_normalizado_valid = _normalizar_texto_busca(txt)

            for palavra_chave, regra in palavras_chave_dict.items():
                palavras_bloqueadas, valid = _listas_regra(regra)

                if any(_contem_expressao(texto_normalizado_valid, bloqueada) for bloqueada in palavras_bloqueadas):
                    continue

                if valid:
                    for expressao in valid:
                        if _contem_expressao(texto_normalizado_valid, expressao) and expressao not in encontradas:
                            encontradas.append(expressao)
                            if modo_itens:
                                return encontradas
                    continue

                chave_com_espacos = palavra_chave.replace("*", "").replace("_", " ")
                chave_norm = unidecode(chave_com_espacos.lower())

                padrao = r"\b" + re.escape(chave_norm).replace(r"\ ", r"[\s\-]+") + r"\b"

                if not re.search(padrao, texto_normalizado):
                    continue
                
                encontradas.append(chave_com_espacos)
                
                if modo_itens:
                    return encontradas

        return encontradas
    
    except Exception as e:
        logs.error(f"Erro ao validar palavras-chave: {e}", exc_info=True)
        return []

def extrair_chaves_do_link(link: str):
    try:
        m = re.search(r"/app/editais/(\d{14})/(\d{4})/(\d+)", link)
        if not m:
            return None
        cnpj, ano, numero = m.group(1), int(m.group(2)), int(m.group(3))
        return cnpj, ano, numero
    except Exception as e:
        logs.error(f"Erro ao extrair chaves do link: {link} - {e}", exc_info=True)
        return None


def extrair_texto(texto, chave):
    try:
        """Extrai o valor associado a uma chave no texto."""
        try:
            return texto.split(chave)[1].split('\n')[0].strip().replace("'", "")
        except IndexError:
            return None
    except Exception as e:
        logs.error(f"Erro ao extrair texto para chave '{chave}': {e}", exc_info=True)
        return None
    
def validar_texto_seguro(texto, filtros_base):
    pos_objeto = texto.lower().find("objeto:")
    if pos_objeto == -1:
        return [] 

    texto_objeto = texto[pos_objeto + len("Objeto:"):].strip()
    texto_normalizado = unidecode(texto_objeto.lower())

    palavras_encontradas = []

    for palavra_chave, palavras_bloqueadas in filtros_base['banco']['palavraschave'].items():
        if palavra_chave not in texto_normalizado:
            continue

        # Bloqueia se encontrar uma palavra proibida
        if any(re.search(rf'\b{re.escape(pb)}\b', texto_normalizado) for pb in palavras_bloqueadas):
            continue

        # Busca todas as palavras do texto original que começam com a palavra-chave
        palavras = texto_objeto.split()
        palavras_encontradas.extend([w.strip(string.punctuation) for w in palavras if unidecode(w.lower()).startswith(palavra_chave)])

    return palavras_encontradas
