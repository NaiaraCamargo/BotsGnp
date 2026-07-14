import locale
import os
import re
from time import sleep
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import unquote_plus
from pncp_shared.logs.controle_logs import logs
from pncp_shared.config.controle_config import configuracoes
 

def validar_campo_banco(key, dic, comprimento):
    try:
        valor = validar_item_key(key, dic, barra_n=False)

        # Se for lista, tenta pegar o primeiro item
        if isinstance(valor, list):
            valor = valor[0] if valor else ""

        # Converte para string e aplica strip
        valor = str(valor).strip()

        if len(valor) > comprimento:
            logs.info(f"{str(key)} maior q {str(comprimento)}, "
                      f"valor formatado: {str(valor[:comprimento])}, "
                      f"valor original: {str(valor)}")
            return valor[:comprimento]

        return valor

    except Exception as e:
        logs.error(f"Erro ao validar campo"
                   f" - Chave: {str(key)},"
                   f" - Comprimento - {str(comprimento)},"
                   f" Valores: {str(dic)} - {str(e)}")
        return ""
    

def validar_item_key(key, dic, key_format="", bold=False, bold_chave=False, is_int=False, barra_n=True, erro=True):
    if key in dic:
        valor_txt = normalizar_valor_para_texto(dic[key]).strip()

        if key_format.strip() != "":
            if bold_chave and not bold:
                key_format = "<b>" + key_format + "</b>"
            mssg = f"{key_format}: {valor_txt}"
        else:
            mssg = valor_txt

        if bold:
            mssg = "<b>" + mssg + "</b>"

        if barra_n:
            mssg += "\n"

        return mssg

    if erro:
        logs.info("A chave:'" + str(key) + "' nao estava presente no retorno")

    if is_int:
        return 0

    return ""

def normalizar_valor_para_texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, list):
        # junta tudo (outra opção: pegar só o primeiro)
        return ", ".join(str(v) for v in valor if v is not None and str(v).strip() != "")
    return str(valor)

def formatar_data(data="", limpar=True, padrao="universal"):
    try:
        if not isinstance(padrao, str):
            padrao = ""

        padrao = padrao.strip()

        if data is None or data == "":
            if limpar:
                return ''
            data = datetime.now()

        if padrao == "universal" or padrao == "":
            data = str(data)
            data = data.split(" ")
            return data[0] + "T03:00:00.000Z"

        elif padrao == "formatado_br":
            return data.strftime("%d/%m/%Y")

        else:
            return data

    except Exception as e:
        logs.error("Nao foi fossivel formatar a data: " + str(data), str(e))
        return ""


def cnpj_formatado(cnpj):
    if len(cnpj) == 14:
        return cnpj[:2] + "." + cnpj[2:5] + "." + cnpj[5:8] + "/" + cnpj[8:12] + "-" + cnpj[12:]

    return cnpj

def limpar_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def limpar_cnpj(cnpj):
    """Remove pontos, barras e traços do CNPJ."""
    return re.sub(r'\D', '', cnpj) if cnpj else cnpj

def remover_acentos(texto):
      return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')

def normalizar_unicode(texto):
    # Remove acentuação e caracteres não-ASCII (último recurso)
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

def normalizar_hifens(texto):
    # Substitui hífens especiais por hífen ASCII padrão "-"
    return re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2212]', '-', texto)

def limpar_para_mysql(texto):
    if texto is None:
        return None
    if not isinstance(texto, str):
        texto = str(texto)

    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.strip()

    return texto

def remover_acentos_ramos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def obter_pastas_download(edital, plataforma):
    try:
        pasta_edital, _ , pasta_comprimidos = obter_caminho_edital(edital, plataforma)
        edital["pasta_edital_original"] = pasta_edital 
        raiz_local = configuracoes.get("raiz_local")
        raiz_server = configuracoes.get("raiz_server")
        pasta_killer = pasta_edital.replace(raiz_local, raiz_server)
        pasta_killer_comprimidos = pasta_comprimidos.replace(raiz_local, raiz_server)
        pasta_killer = os.path.normpath(pasta_killer)
        pasta_killer_comprimidos = os.path.normpath(pasta_killer_comprimidos)
        
        return pasta_killer, pasta_killer_comprimidos
    except Exception as e:
        logs.error(f"Erro ao obter pastas de download: {e}", exc_info=True)
        return None 
    
def obter_caminho_edital(edital, plataforma):
    locale.setlocale(locale.LC_TIME, "Portuguese_Brazil.1252")
    
    # Obter datas
    dia = datetime.today().strftime("%Y-%m-%d")
    dia_obra = datetime.today().strftime("%m.%d")
    ano_atual = datetime.today().strftime("%Y")
    mes_atual = datetime.today().strftime("%B").capitalize()
    mes_atual = mes_atual.upper()

    orgao_edital = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Orgao", "Desconhecido")).strip())
    estado = re.sub(r'[\\/:*?"<>|]', '_', str(edital.get("Uf", "Desconhecido")).strip())
    
    data_raw = str(edital.get("DataFim", dia_obra)).strip()
    data_sem_ano = re.sub(r'/\d{4}$', '', data_raw)
    data_obra = re.sub(r'[\\/:*?"<>|]', '.', data_sem_ano)
    
    pasta_downloads = configuracoes.get('pasta_downloads')
    
    # Caminho das pastas
    pasta_dia = os.path.join(pasta_downloads, f"{ano_atual}/{mes_atual}/{dia}")
    pasta_edital = os.path.join(pasta_dia, f"{data_obra} - {estado} - {orgao_edital}")      
    pasta_comprimidos = os.path.join(pasta_dia,"Arquivos Comprimidos")
    
    return pasta_edital, pasta_dia, pasta_comprimidos

def formatar_valor_sigilo(valor):
    if valor is None:
        return "SIGILOSO"
    if isinstance(valor, str):
        v = valor.strip().replace(".", "").replace(",", ".")
        try:
            valor = float(v)
        except:
            return "SIGILOSO"
    try:
        valor = float(valor)
    except:
        return "SIGILOSO"
    if valor == 0:
        return "SIGILOSO"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def separar_data_hora(dt: str):
    if not dt:
        return None, None
    
    d = datetime.fromisoformat(dt)
    
    data_formatada = d.strftime("%d/%m/%Y")
    hora_formatada = d.strftime("%H:%M")
    
    return data_formatada, hora_formatada

def converter_moeda_brl_para_float(valor):
    try:
        if valor is None:
            return 0

        valor = str(valor).strip()

        if valor.upper() == "SIGILOSO":
            return 0

        valor = valor.replace("R$", "")
        valor = valor.replace(".", "")
        valor = valor.replace(",", ".")
        valor = valor.strip()

        return float(valor)
    except Exception as e:
        logs.error(f"Erro ao converter valor: {valor} - {e}")
        return 0
    
def limpar_arquivo(caminho):
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except Exception as e:
        logs.error(f"Erro ao limpar arquivo: {e}", exc_info=True)
        

def formatar_data_hora_string(data):
    if not data:
        return ""

    try:
        return datetime.strptime(data, "%Y-%m-%dT%H:%M:%S").strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return data
    
def separar_data_hora_formatada(data_hora):
    if not data_hora:
        return "", ""

    try:
        data_hora = str(data_hora).strip()
        data_hora = data_hora.replace("T", " ")

        partes = data_hora.split(" ")

        data = partes[0]
        hora = partes[1] if len(partes) > 1 else ""

        # Converte 2026-06-10 para 10/06/2026
        if "-" in data:
            ano, mes, dia = data.split("-")
            data = f"{dia}/{mes}/{ano}"

        return data, hora

    except Exception as e:
        logs.error("Nao foi possivel separar data e hora: " + str(data_hora), str(e))
        return "", ""
    
def plataforma_tem_itens(plataforma):
    return plataforma.lower() not in ["seguro"]

def format_data(data):
    data = data.split("-")
    return data[2] + "-" + data[1] + "-" + data[0]

def limpar_nome_arquivo(nome):
    nome = re.sub(r'[\\/:*?"<>|]', '_', nome)
    nome = nome.strip()
    return nome or "arquivo"