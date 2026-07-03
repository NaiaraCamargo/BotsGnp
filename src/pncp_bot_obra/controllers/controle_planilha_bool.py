from datetime import datetime, timedelta
from threading import Lock
from email.message import EmailMessage
import os
import smtplib
import xlsxwriter
from pncp_shared.logs.controle_logs import logs
from pncp_shared.utils.funcoespncp import separar_data_hora_formatada

def limpar(valor):
    if not isinstance(valor, str):
        return valor

    return (
        valor.replace("\xa0", " ")
             .replace("R$", "")
             .replace("<b>", "")
             .replace("</b>", "")
             .strip()
    )


def ajustar_largura(col, valor, col_widths):
    texto = str(valor).strip()
    largura = len(texto) + 2

    if texto.startswith("http"):
        max_width = 45
    elif "@" in texto:
        max_width = 25
    elif any(keyword in texto.lower() for keyword in ["descricao", "descrição", "objeto"]):
        max_width = 35
    elif texto.replace(".", "").replace(",", "").isdigit():
        max_width = 12
    elif len(texto) > 200:
        max_width = 35
    else:
        max_width = 22

    largura = min(largura, max_width)

    if col not in col_widths or largura > col_widths[col]:
        col_widths[col] = largura


def pegar_valor(dic, chaves, padrao=""):
    try:
        for chave in chaves:
            valor = dic.get(chave)

            if valor not in [None, ""]:
                return valor

        return padrao
    
    except Exception as e:
        logs.error(f"Erro ao pegar valor do dicionário: {e}", exc_info=True)
        return padrao


def normalizar_palavras_chave(valor):
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor)

    return valor or ""

def gerar_excel_botbool_dia_anterior(processos, pasta_saida="planilhas"):
    try:
        ontem = (datetime.now() - timedelta(days=1)).date()

        if not processos:
            return None, 0

        os.makedirs(pasta_saida, exist_ok=True)

        nome_arquivo = f"editais_botbool_{ontem.strftime('%Y_%m_%d')}.xlsx"
        caminho = os.path.join(pasta_saida, nome_arquivo)

        workbook = xlsxwriter.Workbook(caminho)
        worksheet = workbook.add_worksheet("Editais BotBool")

        col_widths = {}

        colunas_base = [
            ["Data", "data", 10],
            ["Situação", "situacao", 10],
            ["Licitação", "licitacao", 10],
            ["CNPJ", "cnpj", 15],
            ["Órgão", "orgao", 20],
            ["Estado", "uf", 10],
            ["UASG", "codigo_unidade_compradora", 10],
            ["Número", "numero", 10],
            ["Número Aux", "numero_aux", 10],
            ["Data de Abertura", "data_abertura", 15],
            ["Hora", "hora_abertura", 10],
            ["N° Itens", "quantidade_total_itens", 10],
            ["Valor Estimado", "valor_total_estimado_compra", 15],
            ["Palavras-chave", "palavras_chave", 20],
            ["Link", "link", 50],
            ["Link Auxiliar", "link_auxiliar", 50],
            ["Descrição", "descricao", 35],
        ]

        maior_qtd_itens = max(
            len(processo.get("itens", []))
            for processo in processos
        )

        cabecalho = [col[0] for col in colunas_base]

        if maior_qtd_itens > 0:
            for i in range(1, maior_qtd_itens + 1):
                cabecalho += [
                    f"Item {i} Nº",
                    f"Item {i} Descrição",
                    f"Item {i} Quantidade",
                    f"Item {i} Valor Unitário",
                    f"Item {i} Valor Total",
                ]

        worksheet.write_row(0, 0, cabecalho)

        for col_idx, titulo in enumerate(cabecalho):
            ajustar_largura(col_idx, titulo, col_widths)

        linha_excel = 1

        for processo in processos:
            linha = []
            
            data, hora = separar_data_hora_formatada(processo.get("data_fim_recebimento_proposta", ""))
            
            if data and hora:
                processo["data_abertura"] = data
                processo["hora_abertura"] = hora
            else:
                processo["data_abertura"] = ""
                processo["hora_abertura"] = ""

            for titulo, campo, _ in colunas_base:
                valor = processo.get(campo, "")            
                valor = limpar(str(valor))
                linha.append(valor)

            itens = processo.get("itens", [])

            for item in itens:
                linha.append(pegar_valor(item, ["numero_item", "numeroItem", "numero", "numeroItemCompra"]))
                linha.append(pegar_valor(item, ["descricao_item", "descricaoItem", "descricao", "descricaoItemCompra"]))
                linha.append(pegar_valor(item, ["quantidade_item", "quantidadeItem", "quantidade"]))
                linha.append(pegar_valor(item, ["valor_unit_item", "valorUnitario", "valor_unitario", "valorUnitarioEstimado"]))
                linha.append(pegar_valor(item, ["valor_total_item", "valorTotal", "valor_total", "valorTotalEstimado"]))

            itens_faltando = maior_qtd_itens - len(itens)

            if itens_faltando > 0:
                linha += [""] * (itens_faltando * 5)

            worksheet.write_row(linha_excel, 0, linha)

            for col_idx, valor in enumerate(linha):
                ajustar_largura(col_idx, valor, col_widths)

            linha_excel += 1

        for col_idx, largura in col_widths.items():
            worksheet.set_column(col_idx, col_idx, largura)

        bold_format = workbook.add_format({"bold": True, "align": "center"})
        worksheet.set_row(0, None, bold_format)
        worksheet.autofilter(0, 0, linha_excel - 1, len(cabecalho) - 1)
        worksheet.freeze_panes(1, 0)

        workbook.close()

        return caminho, linha_excel - 1
    
    except Exception as e:
        logs.error(f"Erro ao gerar planilha Excel BotBool: {e}", exc_info=True)
        return None, 0


def enviar_email_com_planilha( caminho_arquivo: str, emails_destino: list, assunto: str, corpo: str, email_remetente: str,
                              senha_email: str, smtp_host: str = "smtp.gmail.com", smtp_port: int = 587):
    try:
        if not caminho_arquivo or not os.path.exists(caminho_arquivo):
            return False

        if not emails_destino:
            return False

        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = email_remetente
        msg["To"] = ", ".join(emails_destino)
        msg.set_content(corpo)

        with open(caminho_arquivo, "rb") as arquivo:
            conteudo = arquivo.read()
            nome_arquivo = os.path.basename(caminho_arquivo)

        msg.add_attachment(
            conteudo,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=nome_arquivo
        )

        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(email_remetente, senha_email)
            smtp.send_message(msg)

        return True
    except Exception as e:
        logs.error(f"Erro ao enviar email com planilha: {e}", exc_info=True)
        return False