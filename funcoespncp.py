import html
import os
import re
import logging
from time import sleep
from requests import post
from datetime import datetime, timedelta
from calendar import monthrange
from unidecode import unidecode
import json

import requests

logs = logging.getLogger('logger1')

usuariosNotificar = []
configuracoes = {
    "token_telegram": "",
    "token_telegram_alterados": "",
    "dias_limpar_logs": 30,
    "conexao_banco": {
        "host": "",
        "port": 3306,
        "user": "",
        "password": "",
        "database": ""
    },
    "UNRAR_TOOL":"",
    "pasta_downloads": "",
    "raiz_local": "",
    "raiz_server": "",
    "extensoes_imgs": [],
    "extensoes_planilhas": [],
    "formatos_para_docx": [],
    "extensoes_validas": [],
    "limite_kb": 10000,
    "processar_todos_obra": True,
    "processar_todos_pintura": True,
    "processar_todos_reforma": True,
    "processar_dia": True
}

CAMINHO_CONFIG = "config.json"

def controle_logs(pasta=""):
    global logs

    try:
        hoje = datetime.now()

        if not os.path.isdir("logs"):
            os.makedirs("logs")

        caminho = "logs"
        if pasta != "":
            subpasta = os.path.join("logs", pasta)
            if not os.path.isdir(subpasta):
                os.makedirs(subpasta)
            caminho = subpasta

        if logs.hasHandlers():
            logs.handlers.clear()

        logs.setLevel(logging.DEBUG)
        handler1 = logging.FileHandler(
            os.path.join(caminho, f"{hoje.date()}.log"),
            encoding='utf-8'
        )
        handler1.setLevel(logging.DEBUG)
        handler1.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S"))
        logs.addHandler(handler1)

        dias_limpar_logs = configuracoes.get('dias_limpar_logs', 30)
        menos_dias = (hoje - timedelta(days=dias_limpar_logs)).date()

        for arq in os.listdir(caminho):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}.log", arq):
                nome_data = arq[:-4]
                try:
                    data_arquivo = datetime.strptime(nome_data, "%Y-%m-%d").date()
                    if data_arquivo < menos_dias:
                        os.remove(os.path.join(caminho, arq))
                except ValueError:
                    pass

    except Exception as e:
        logs.error(f"Controle Logs: {e}")


def carregar_configuracoes():
    global configuracoes

    try:
        if os.path.isfile(CAMINHO_CONFIG):
            with open(CAMINHO_CONFIG, "r", encoding="utf-8") as f:
                carregado = json.load(f)
                configuracoes.update(carregado)
        else:
            with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
                json.dump(configuracoes, f, indent=4)
            raise Exception(f"Arquivo '{CAMINHO_CONFIG}' criado. Configure os valores antes de continuar.")
        sleep(1)
    except Exception as e:
        print("Erro ao carregar configurações:", e)
        raise



def atualizar_arquivo_configuracoes():
    try:
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(configuracoes, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print("Erro ao salvar configurações:", e)
        raise


def config(nome, texto=True):
    if nome in configuracoes["conexao_banco"]:
        return str(configuracoes["conexao_banco"][nome]) if texto else configuracoes["conexao_banco"][nome]
    elif nome in configuracoes:
        return str(configuracoes[nome]) if texto else configuracoes[nome]
    else:
        print(f"Configuração '{nome}' não encontrada.")
        return None


def enviar_mensagem(msg, usuarios_notificar, novo_processo, erro = False):
    try:
        msg = formatar_mensagem_pncp(msg, erro)

        token_enviar = configuracoes.get('token_telegram', "")

        if not novo_processo and configuracoes.get('token_telegram_alterados', "") != "":
            token_enviar = configuracoes.get('token_telegram_alterados', "")
            logs.info(f"Enviar Mensagem: Token Telegram configurado para - {token_enviar}")

        if msg != "" and token_enviar != "":
            for usuario_notificar in usuarios_notificar:
                tentativas = 3
                for tentativa in range(tentativas):
                    try:
                        # Montando a URL para enviar a mensagem ao Telegram
                        url = f"https://api.telegram.org/bot{token_enviar}/sendMessage"

                        payload = {
                            'chat_id': usuario_notificar,
                            'parse_mode': 'HTML',
                            'text': msg,
                            'disable_web_page_preview': True
                        }

                        response = requests.post(url, data=payload)
                        
                        if response.status_code == 200:
                            logs.info(f"Enviar Mensagem: Enviado para {usuario_notificar} - edital: {msg}")
                        else:
                            logs.error(f"Erro no envio da mensagem para {usuario_notificar}. Código de status: {response.text}\n")

                        sleep(1)
                        break  # Envia a mensagem e sai do loop de tentativas
                    except Exception as ee:
                        if tentativa < tentativas - 1:
                            logs.warning(f"Tentativa {tentativa + 1} falhou. Tentando novamente...")
                            sleep(2)
                        else:
                            logs.error(f"Erro Enviar Mensagem: Não foi possível enviar para: {usuario_notificar}. Erro: {str(ee)}")
        else:
            logs.warning("Mensagem ou token de envio inválido.")
    except Exception as e:
        logs.error(f"Erro ao enviar a mensagem: {str(e)}")


def validar_campo_banco(key, dic, comprimento):
    try:
        valor = validar_item_key(key, dic, barra_n=False).strip()

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


def validar_item_key(key, dic, key_format="", bold=False, bold_chave=False, is_int=False, barra_n=True, erro=True):
    if key in dic:
        if key_format.strip() != "":
            if bold_chave and not bold:
                key_format = "<b>" + key_format + "</b>"
            mssg = key_format + ": " + dic[key]
        else:
            mssg = dic[key]

        if bold:
            mssg = "<b>" + mssg + "</b>"

        mssg = mssg.strip()
        if barra_n:
            mssg = mssg + "\n"

        return mssg

    if erro:
        logs.info("A chave:'" + str(key) + "' nao estava presente no retorno")

    if is_int:
        return 0

    return ""


def liberar_notificacao(edital, novo=True):
    # Esses sao os status que buscamos
    #   NOVOS
    #       PUBLICADO
    #       RECEPÇÃO DE PROPOSTAS
    #       Recebendo Propostas

    #   ALTERACOES
    #       Suspenso - Antes da Abertura
    #       Cancelado

    if not edital.get("notificar_retorno", False):
        return False

    aux = unidecode(edital.get("Situacao", edital.get("SituacaoAtual", "")).replace(" ", '').casefold())
    if novo and (aux == "publicado" or aux == "publicada" or aux == "recepcaodepropostas" or aux == "recepcaodeproposta"
                 or aux == "recebendopropostas" or aux == "recebendoproposta" or aux == "aguardandoinicioderecebimentodepropostas"
                 or aux == "aguardandoinicioderecebimentodeproposta"):
        logs.info(f"Novo, Palavras Chave: {str(edital.get('palavras_chave'))}")
        return True

    elif novo and (aux == "suspenso-antesdaabertura" or aux == "cancelado"):
        logs.info(f"Edital nao encontrado no banco, porem veio com status '{str(aux)}'")

    elif not novo and (aux == "publicado" or aux == "publicada" or aux == "recepcaodepropostas"
                       or aux == "recepcaodeproposta" or aux == "recebendopropostas" or aux == "recebendoproposta"
                       or aux == "suspenso-antesdaabertura" or aux == "cancelado" or aux == "aguardandoinicioderecebimentodepropostas"
                       or aux == "aguardandoinicioderecebimentodeproposta"):
        logs.info(f"Existe, Palavras Chave: {str(edital.get('palavras_chave'))}")
        return True

    return False

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


def cnpj(cnpj):
    if len(cnpj) == 14:
        return cnpj[:2] + "." + cnpj[2:5] + "." + cnpj[5:8] + "/" + cnpj[8:12] + "-" + cnpj[12:]

    return cnpj

def limpar_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def formatar_mensagem_pncp(msg_dict, erro):
    try:
        if type(msg_dict) != dict:
            return msg_dict
        
        if erro:
            nova_msg = "<b>=============================================================================================</b>\n"
            nova_msg += "\n"
            nova_msg += "<b>POSSÍVEL ERRO NO SITE... EXTRAÇÃO DE MAIS DE 3 LINKS COM TIMEOUT. NÃO SERÁ MAIS PROCESSADO NENHUM EDITAL!</b>\n"
            nova_msg += "\n"
            nova_msg += "<b>AGUARDANDO 5 MINUTOS PARA NOVA TENTATIVA ... </b>\n"
            nova_msg += "\n"
            nova_msg += "<b>=============================================================================================</b>"
            return html.unescape(nova_msg.strip())


        # Identificação do tipo de alteração
        if any(key.startswith("status_processo") for key in msg_dict):
            nova_msg = "ALTERAÇÃO DE PROCESSO LOCALIZADO\n"
            if 'status_processo_situacao' in msg_dict:
                nova_msg += "<b>ALTERAÇÃO DE SITUAÇÃO</b>\n"
            elif 'status_processo_data_fim' in msg_dict:
                nova_msg += "<b>ALTERAÇÃO DE DATA DO FIM RECEBIMENTO PROPOSTA</b>\n"
            elif 'status_processo_arquivos' in msg_dict:
                nova_msg += "<b>NOVOS ARQUIVOS ENCONTRADOS</b>\n"
            elif 'status_processo_itens' in msg_dict:
                nova_msg += "<b>NOVOS ITENS ENCONTRADOS</b>\n"

        nova_msg = "\n"
        # Situações
        if "Situacao" in msg_dict:
            nova_msg += f"<b>SITUAÇÃO:</b> <code>{html.escape(str(msg_dict['Situacao']))}</code>\n"
        if "SituacaoAnterior" in msg_dict:
            nova_msg += f"<b>SITUAÇÃO ANTERIOR:</b> {html.escape(str(msg_dict['SituacaoAnterior']))}\n"
        if "SituacaoAtual" in msg_dict:
            nova_msg += f"<b>SITUAÇÃO ATUAL:</b> {html.escape(str(msg_dict['SituacaoAtual']))}\n"

        nova_msg += "\n"

        # Dados principais
        if "Licitacao" in msg_dict:
            nova_msg += f"<b>LICITAÇÃO:</b> <code>{html.escape(str(msg_dict['Licitacao']))}</code>\n\n"
        if "Cnpj" in msg_dict:
            msg_dict['Cnpj'] = cnpj(msg_dict.get("Cnpj", ""))
            nova_msg += f"<b>CNPJ:</b> <code>{html.escape(str(msg_dict['Cnpj']))}</code>\n\n"
        if "Orgao" in msg_dict:
            nova_msg += f"<b>ORGÃO:</b> <code>{html.escape(str(msg_dict['Orgao']))}</code>\n\n"
        if "Uf" in msg_dict:
            nova_msg += f"<b>ESTADO:</b> <code>{html.escape(str(msg_dict['Uf']))}</code>\n\n"
        if "CodigoUnidadeCompradora" in msg_dict:
            nova_msg += f"<b>UASG:</b> <code>{html.escape(str(msg_dict['CodigoUnidadeCompradora']))}</code>\n\n"
        if "Numero" in msg_dict:
            nova_msg += f"<b>NÚMERO:</b> <code>{html.escape(str(msg_dict['Numero']))}</code>\n\n"
        if "NumeroAux" in msg_dict:
            nova_msg += f"<b>NÚMERO AUX:</b> <code>{html.escape(str(msg_dict['NumeroAux']))}</code>\n\n"

        # Datas e modo de disputa
        if 'status_processo_data_fim' in msg_dict:
            nova_msg += f"<b>DATA FIM PROPOSTA ANTERIOR:</b> {html.escape(str(msg_dict.get('DataFimAnterior', '')))}\n\n"
            nova_msg += f"<b>DATA FIM PROPOSTA ATUAL:</b> {html.escape(str(msg_dict.get('DataFimAtual', '')))}\n\n"
        else:
            if "DataFimRecebimentoProposta" in msg_dict:
                nova_msg += f"<b>DATA DE ABERTURA:</b> <code>{html.escape(str(msg_dict['DataFim']))}</code>\n\n"
                nova_msg += f"<b>HORA:</b> <code>{html.escape(str(msg_dict['HoraFim']))}</code>\n\n"
            
        if "ModoDeDisputa" in msg_dict:
            nova_msg += f"<b>MODALIDADE DE DISPUTA:</b> <code>{html.escape(str(msg_dict['ModoDeDisputa']))}</code>\n\n"

        # Arquivos e itens
        if 'status_processo_arquivos' in msg_dict:
            nova_msg += f"<b>N° ARQUIVOS ENCONTRADOS:</b> {msg_dict.get('arquivosBaixados', '')}\n\n"

        if 'status_processo_itens' in msg_dict:
            if "QuantidadeAnterior" in msg_dict:
                nova_msg += f"<b>N° ITENS ANTERIORES:</b> {html.escape(str(msg_dict['QuantidadeAnterior']))}\n\n"
            if "QuantidadeAtual" in msg_dict:
                nova_msg += f"<b>N° ITENS ATUAL:</b> {html.escape(str(msg_dict['QuantidadeAtual']))}\n\n"
        elif "QuantidadeItens" in msg_dict:
            nova_msg += f"<b>N° ITEN:</b> <code>{html.escape(str(msg_dict['QuantidadeItens']))}</code>\n\n"

        if "ValorTotalEstimadoCompra" in msg_dict:
            nova_msg += f"<b>VALOR ESTIMADO:</b> <code>{html.escape(str(msg_dict['ValorTotalEstimadoCompra']))}</code>\n\n"

        # Links
        if "Link" in msg_dict:
            nova_msg += f"<b>Link:</b> {html.escape(str(msg_dict['Link']))}\n\n"
        if "LinkBotao" in msg_dict:
            nova_msg += f"<b>LINK AUXILIAR:</b> {html.escape(str(msg_dict['LinkBotao']))}\n\n"

        # Descrição
        if "Descricao" in msg_dict:
            nova_msg += f"<b>DESCRIÇÃO:</b> {str(msg_dict['Descricao'])}\n\n"

        # Pasta download
        if "pasta_download" in msg_dict:
            nova_msg += f"<b>PASTA TMP DOWNLOAD:</b> <code>{html.escape(msg_dict['pasta_download'], quote=False)}</code>\n"
        if "pasta_download" in msg_dict:
            nova_msg += f"<b>PASTA COMPRIMIDOS:</b> <code>{html.escape(msg_dict['pasta_comprimidos'], quote=False)}</code>\n"
            
        return html.unescape(nova_msg.strip())

    except Exception as e:
        logs.error(f"Não foi possível formatar a mensagem: {str(e)}")
        return ""
    
def limpar_cnpj(cnpj):
    """Remove pontos, barras e traços do CNPJ."""
    return re.sub(r'\D', '', cnpj) if cnpj else cnpj

def gerar_urls_base():
    urls_geradas = []
    base_url = "https://pncp.gov.br/app/editais?q={palavra}&&status=recebendo_proposta&pagina=1"
    
    for item in configuracoes.get("urls", []):
        palavra_chave = item.get("palavra_chave", "")
        if palavra_chave:
            url_formatada = base_url.format(palavra=palavra_chave)
            urls_geradas.append({
                "url": url_formatada,
                "palavra_chave": palavra_chave,
                "excecoes": item.get("excecoes", [])
            })
    
    return urls_geradas
