from funcoespncp import carregar_configuracoes
from repositoriopncp import retornar_periodo_processos, retornar_processos
import xlsxwriter
import webview
import os
import pandas as pd
import re


# pyinstaller --add-data "gerar_planilha_obra.html;." gerar_planilha_obra.py --onefile --noconsole

def format_data(data):
    data = data.split("-")
    return data[2] + "-" + data[1] + "-" + data[0]


def verificar_existencia_planilha(nome):
    for n in os.listdir():
        if n.endswith(".xlsx"):
            n = n.split(".xlsx")[0].strip()
            if n == nome:
                return True
    return False


def limpar_nome_arquivo(nome):
    nome = re.sub(r'[\\/:*?"<>|]', '_', nome)
    nome = nome.strip()
    return nome or "arquivo"

def retornar_nome_planilha(plataforma, d_i, d_f, link):
    nome = "planilha"

    if plataforma != "" and plataforma != "todos":
        nome = nome + "_" + plataforma

    try:
        if link != "":
            nome += "_" + limpar_nome_arquivo(link)   
        else:
            d1, d2 = retornar_periodo_processos()
            if d_i == "":
                d_i = d1

            if d_f == "":
                d_f = d2

            if d_i != "":
                nome += "_" + format_data(d_i)

            if d_f != "":
                nome += "_" + format_data(d_f)
    except:
        return True, "Não foi possível se conectar ao banco de dados, verifique se a configuração de conexão " \
                     "no arquivo .config está correta."

    nome_final = limpar_nome_arquivo(nome)
    return False, nome_final

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
    largura = len(texto) + 2  # margem
    
    # --- limites por categoria ---
    if texto.startswith("http"):
        max_width = 45  # links
    elif "@" in texto:
        max_width = 25  # emails, caso apareça
    elif any(keyword in texto.lower() for keyword in ["descricao", "descrição"]):
        max_width = 30
    elif texto.replace('.', '').replace(',', '').isdigit():
        max_width = 12  # números, valores
    elif len(texto) > 200:
        max_width = 30  # descrições muito grandes
    else:
        max_width = 20  # padrão geral

    largura = min(largura, max_width)
    
    if col not in col_widths or largura > col_widths[col]:
        col_widths[col] = largura

def gerar_excel(filtros, nome):
    try:
        processos  = retornar_processos(filtros)
    
        if not processos:
            return 0

        workbook = xlsxwriter.Workbook(nome + '.xlsx')
        worksheet = workbook.add_worksheet()
        
        col_widths = {}

        colunas_base = [
            ['Data', 'data', 10],
            ['Situação', 'situacao', 10],
            ['Licitação', 'licitacao', 10],
            ['CNPJ', 'cnpj', 15],
            ['Órgão', 'orgao', 20],
            ['Estado', 'uf', 10],
            ['UASG', 'codigo_unidade_compradora', 10],
            ['Número', 'numero', 10],
            ['Número Aux', 'numero_aux', 10],
            ['Data de Abertura', 'data_abertura', 10],
            ['Hora', 'hora_abertura', 10],
            ['N° Itens', 'quantidade_total_itens', 10],
            ['Valor Estimado', 'valor_total_estimado_compra', 10],
            ['Link', 'link', 50],
            ['Link Auxiliar', 'link_auxiliar', 50],
            ['Descrição', 'descricao', 30],
        ]
        
        maior_qtd_itens = max(len(x["itens"]) for x in processos)
        # Cabeçalho
        cabecalho = [col[0] for col in colunas_base]
        
        for i in range(1, maior_qtd_itens + 1):
            cabecalho += [
                f"Item {i} Nº",
                f"Item {i} Descrição",
                f"Item {i} Quantidade",
                f"Item {i} Valor Unitário",
                f"Item {i} Valor Total",
            ]

        # Escrever cabeçalho
        worksheet.write_row(0, 0, cabecalho)
        
        for col_idx, titulo in enumerate(cabecalho):
            ajustar_largura(col_idx, titulo, col_widths)
       
        linha_excel = 1
        for processo in processos:
            itens = processo["itens"]
            linha = []
              
            # extrair data e hora do campo varchar
            raw_datahora = limpar(processo.get("data_fim_recebimento_proposta", ""))
            
            if " " in raw_datahora:
                processo["data_abertura"], processo["hora_abertura"] = raw_datahora.split(" ")
            else:
                processo["data_abertura"] = raw_datahora
                processo["hora_abertura"] = ""
            
            for titulo, campo, _ in colunas_base:
                valor = limpar(str(processo.get(campo, "")))
                linha.append(valor)

            for item in itens:
                linha.append(item["numero_item"])
                linha.append(item["descricao_item"])
                linha.append(item["quantidade_item"])
                linha.append(item["valor_unit_item"])
                linha.append(item["valor_total_item"])

            itens_faltando = maior_qtd_itens - len(itens)
            linha += [""] * (itens_faltando * 4)
            
            worksheet.write_row(linha_excel, 0, linha)
            
            for col_idx, valor in enumerate(linha):
                ajustar_largura(col_idx, valor, col_widths)
                
            linha_excel += 1
            
        for col_idx, largura in col_widths.items():
            worksheet.set_column(col_idx, col_idx, largura)
            
        bold_format = workbook.add_format({'bold': True, 'align': 'center'})
        worksheet.set_row(0, None, bold_format)
        worksheet.autofilter(0, 0, linha_excel - 1, len(cabecalho) - 1)
        worksheet.freeze_panes(1, 0)

        workbook.close()
        return linha_excel - 1

    except Exception as e:
        print(f"Erro ao gerar planilha: {e}")
        return f"Não foi possível gerar a planilha {e}."


def gerar_excel_registros(processos, plataforma, registros_novos):
    arquivo = str(plataforma + '_new_registros.xlsx')

    try: 
        if not os.path.exists(arquivo):
            print('Criando novo arquivo de registros...')
            criar_excel_registros(plataforma)
        if registros_novos:
            adicionar_registros(processos, arquivo,plataforma)
        else:
            atualizar_registros(processos, arquivo)
    except Exception as e:
        print(e)


def criar_excel_registros(plataforma):
    try:
        if str(plataforma).strip() == '':
            raise Exception('Não foi possível identificar o bot!')

        workbook = xlsxwriter.Workbook(str(plataforma) + '_new_registros.xlsx')
        worksheet = workbook.add_worksheet()
       
        #  Nome da coluna, Tamanho da célula  
        dados = (['Situação', 10],['Licitação', 10],['CNPJ', 15],['Órgão', 20],['Estado', 10],['UASG', 10],['Número', 10],
                    ['Número Aux', 10], ['Data de Abertura', 10], ['Hora', 10], ['Modalidade de Disputa', 20], ['N° Itens', 10], 
                    ['Valor Estimado', 10], ['Link', 50],['Link Auxiliar', 50],  ['Descrição', 30])     
    
        cabecalho = ()
        for d in dados:
            cabecalho = cabecalho + (d[0],)
        worksheet.write_row(0, 0, cabecalho)

        for col_num in range(len(dados)):
            worksheet.set_column(col_num, col_num, dados[col_num][1] + 4)

        bold_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
        worksheet.set_row(0, None, bold_format)
        worksheet.freeze_panes(1, 0)
        workbook.close()
    except Exception as e:
        print('Erro: ' + str(e))


def adicionar_registros(processos, arquivo):
    try:
        df = pd.read_excel(arquivo)
       
        for processo in processos:
            registros = pd.DataFrame({
                'Situação': [processo.get('Situacao')],
                'Licitação': [processo.get('Licitacao')],
                'CNPJ': [processo.get('Cnpj')],
                'Órgão': [processo.get('Orgao')],
                'Estado': [processo.get('Uf')],
                'UASG': [processo.get('CodigoUnidadeCompradora')],
                'Número': [processo.get('Numero')],
                'Número Aux': [processo.get('NumeroAux')],
                'Data de Abertura': [processo.get('DataFim')],
                'Hora': [processo.get('HoraFim')],
                'Modalidade de Disputa': [processo.get('ModoDeDisputa')],
                'N° Itens': [processo.get('QuantidadeItens')],
                'Valor Estimado': [processo.get('ValorTotalEstimadoCompra')],
                'Link': [processo.get('Link')],
                'Link Auxiliar': [processo.get('LinkBotao')],
                'Descrição': [processo.get('Descricao')]
            })

            df = pd.concat([df, registros], ignore_index=True)
                     
        df.to_excel(arquivo, index=False)
    except Exception as e:
        print(e)


def atualizar_registros(processos, arquivo):
    try:
        df = pd.read_excel(arquivo)

        for processo in processos:
            linha = df[df['Link'] == processo['Link']].index

            if not linha.empty:
                df.loc[linha[0], 'Data Registro'] = processo['Data']
                df.loc[linha[0], 'CNPJ'] = processo['Cnpj']
                df.loc[linha[0], 'Órgão'] = processo['Orgao']
                df.loc[linha[0], 'Número'] = processo['Numero']
                df.loc[linha[0], 'Data'] = processo['Data']

        df.to_excel(arquivo, index=False)
    except Exception as e:
        print(e)


def js(window):
    pass


nome = ""
filtros = {}
class Api:
    def gerarPlanilha(self, tipo_data, data_inicial, data_final, plataforma, link_edital):
        global nome, filtros

        try:
            carregar_configuracoes()
        except:
            return "<p style='color:red;'>Arquivo de configuracao de conexão do banco de dados .json não localizado.</p>"

        filtros['data_inicial'] = data_inicial.strip()
        filtros['data_final'] = data_final.strip()
        filtros['tipo_data'] = tipo_data.strip()
        filtros['plataforma'] = plataforma.strip().lower()
        filtros['link_edital'] = link_edital.strip() 

        if tipo_data == "por_periodo" and filtros['data_inicial'] == "" and filtros['data_final'] == "":
            return "<p style='color:red;'>Deve ser informada a Data Inicial ou a Data Final " \
                           "ou marcar a opção para gerar Todos os Registros</p>"
                           
        if tipo_data == "por_link_edital" and  filtros['link_edital'] == "":
            return "<p style='color:red;'>Deve ser informada o link do Edital</p>"
            

        erro, nome = retornar_nome_planilha(plataforma, data_inicial, data_final, link_edital)

        if erro:
            return f"<p style='color:red;'>{nome}</p>"

        if verificar_existencia_planilha(nome):
            window.evaluate_js("abrirModal()")
        else:
            qtd_registros = gerar_excel(filtros, nome)

            if type(qtd_registros) == int:
                if qtd_registros == 0:
                    return "<p style='color:blue;'>Nenhum registro encontrado para os filtros aplicados</p>"
                else:
                    return f"<p style='color:green;'>Planilha gerada, você já pode fechar essa janela. " \
                           f"<br><br>Quantidade de registros: {qtd_registros}</p>"
            else:
                return f"<p style='color:red;'>{qtd_registros}</p>"

    def prosseguirGeracaoPlanilha(self, valor):
        global nome, filtros

        if valor:
            qtd_registros = gerar_excel(filtros, nome)
            if type(qtd_registros) == int:
                if qtd_registros == 0:
                    return "<p style='color:blue;'>Nenhum registro encontrado para os filtros aplicados</p>"
                else:
                    return f"<p style='color:green;'>Planilha gerada, você já pode fechar essa janela. " \
                           f"<br><br>Quantidade de registros: {qtd_registros}</p>"
            else:
                return f"<p style='color:red;'>{qtd_registros}" \
                       f"<br>Verifique se não existe uma planilha aberta com o nome: '{nome}'</p></p>"
        else:
            return "<p style='color:blue;'>Geração da Planilha Cancelada</p>"


if __name__ == '__main__':
    api = Api()
    window = webview.create_window('Gerar Planilha', 'gerar_planilha_obra.html', js_api=api, height=680)
    webview.start(func=js, args=window, debug=False)
