from time import sleep
import requests
import html
import re

from pncp_shared.logs_pncp.controle_logs import logs
from pncp_shared.config.controle_config import configuracoes
from pncp_shared.utils.funcoespncp import cnpj_formatado


def enviar_mensagem(msg, usuarios_notificar,  botGnp=False, botBool=False, erro = False):
    try:
        link_edital = msg.get("Link", "sem_link") if isinstance(msg, dict) else "sem_link"
        
        msg = formatar_mensagem(msg, erro)

        token_enviar = configuracoes.get('token_telegram_obras', "")
        
        usuarios_envio = usuarios_notificar.copy()

        if not erro:
            if not botGnp:
                usuarios_envio.remove('-1002657878005') if '-1002657878005' in usuarios_envio else None

            if not botBool:
                usuarios_envio.remove('-1004295198662') if '-1004295198662' in usuarios_envio else None
       
        if msg  != "" and token_enviar != "":
            for usuario_notificar in usuarios_envio:
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
                            logs.info(f"Enviar Mensagem: Enviado para {usuario_notificar} - edital: {link_edital}")
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
        
def formatar_mensagem(msg_dict, erro):
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
            msg_dict['Cnpj'] = cnpj_formatado(msg_dict.get("Cnpj", ""))
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

        # Coleta todos os índices únicos das chaves relevantes
        indices = set()
        for chave in msg_dict:
            m = re.fullmatch(r"(?:link_reserva|reserva_perdida|ramo|ramo_perdido)_(\d+)", chave)
            if m:
                indices.add(int(m.group(1)))

        # Monta a mensagem por índice, com o ramo abaixo da reserva correspondente
        for i in sorted(indices):
            link_key = f"link_reserva_{i}"
            perdida_key = f"reserva_perdida_{i}"
            ramo_key = f"ramo_{i}"
            ramo_perdido_key = f"ramo_perdido_{i}"

            if link_key in msg_dict:
                nova_msg += f"<b>Reserva {i}:</b> {html.escape(str(msg_dict[link_key]))}\n"
                if ramo_key in msg_dict:
                    nova_msg += f"<b>RAMO {i}:</b> {html.escape(str(msg_dict[ramo_key]))}\n"
                nova_msg += "\n"

            if perdida_key in msg_dict:
                nova_msg += f"<b>Reserva Perdida {i}:</b> {html.escape(str(msg_dict[perdida_key]))}\n"
                if ramo_perdido_key in msg_dict:
                    nova_msg += f"<b>RAMO Perdido {i}:</b> {html.escape(str(msg_dict[ramo_perdido_key]))}\n"
                nova_msg += "\n"

                
        if "aviso_reserva" in msg_dict:
            aviso = str(msg_dict["aviso_reserva"]).strip()
            aviso = html.escape(aviso)  # Escapa caracteres especiais HTML
            nova_msg += f"<b>⚠️ AVISO RESERVA:</b> {aviso}\n\n"
         
        #if "horario_termino" in msg_dict:
            #nova_msg += f"<b>TEMPO DE PROCESSAMENTO:</b> <code>{html.escape(str(msg_dict['horario_termino']))}</code>\n\n"
        
        if "codigos_catalogo" in msg_dict:
            nova_msg += f"<b>ITENS VALIDOS: </b> {html.escape(str(msg_dict['codigos_catalogo']))}\n\n"
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
  
    