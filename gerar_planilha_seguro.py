import datetime
from funcoespncp import carregar_configuracoes
from repositoriopncp import retornar_periodo_processos, retornar_processos
import xlsxwriter
import webview
import os
import pandas as pd


# pyinstaller --add-data "gerar_planilha.html;." gerar_planilha.py --onefile --noconsole

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


def retornar_nome_planilha(plataforma, d_i, d_f):
    nome = "planilha"

    if plataforma != "" and plataforma != "todos":
        nome = nome + "_" + plataforma

    try:
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

    return False, nome


def gerar_excel(filtros, nome):
    try:
        processos = retornar_processos(filtros)
        qtd_total = len(processos)

        if qtd_total == 0:
            return 0

        workbook = xlsxwriter.Workbook(nome + '.xlsx')
        worksheet = workbook.add_worksheet()

        colunas = [
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

        # Cabeçalho
        cabecalho = [col[0] for col in colunas]
        worksheet.write_row(0, 0, cabecalho)

        linha_excel = 1
        for processo in processos:
            linha = []
              
            # extrair data e hora do campo varchar
            datahora = (processo.get('data_fim_recebimento_proposta') or "").strip()
            if ' ' in datahora:
                data_abertura, hora_abertura = datahora.split(' ')
            else:
                data_abertura = datahora
                hora_abertura = ''

            processo['data_abertura'] = data_abertura
            processo['hora_abertura'] = hora_abertura

            for idx, (titulo, campo, largura) in enumerate(colunas):
                valor = processo.get(campo, "")
                if isinstance(valor, str):
                    valor = valor.replace("<b>", "*").replace("</b>", "*")
                valor_str = str(valor)

                # Ajusta largura se necessário
                if len(valor_str) > colunas[idx][2]:
                    colunas[idx][2] = len(valor_str)

                linha.append(valor_str)

            worksheet.write_row(linha_excel, 0, linha)
            linha_excel += 1

        # Ajustar larguras de colunas
        for col_num, (_, _, largura) in enumerate(colunas):
            worksheet.set_column(col_num, col_num, largura + 4)

        # Formatação
        bold_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
        worksheet.set_row(0, None, bold_format)
        worksheet.autofilter(0, 0, linha_excel - 1, len(cabecalho) - 1)
        worksheet.freeze_panes(1, 0)

        workbook.close()
        return linha_excel - 1

    except Exception as e:
        print(f"Erro ao gerar planilha: {e}")
        return "Não foi possível gerar a planilha."


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
       
        if plataforma == 'obra':    
            #  Nome da coluna, Tamanho da célula  
            dados = (['Situação', 10],['Licitação', 10],['CNPJ', 15],['Órgão', 20],['Estado', 10],['UASG', 10],['Número', 10],
                      ['Número Aux', 10], ['Data de Abertura', 10], ['Hora', 10], ['Modalidade de Disputa', 20], ['N° Itens', 10], 
                      ['Valor Estimado', 10], ['Link', 50],['Link Auxiliar', 50],  ['Descrição', 30])     
        else:
            #  Nome da coluna, Tamanho da célula
            dados = (['Data Inicio', 10], ['Data Fim', 10], ['CNPJ', 15], ['Órgão', 20], ['Número', 10], ['Data Divulgação', 10], 
                     ['Valor Estimado', 10], ['Link', 50])
             
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


def adicionar_registros(processos, arquivo, plataforma):
    try:
        df = pd.read_excel(arquivo)
        if plataforma == 'obra':    
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

        else:
            for processo in processos:
                registros = pd.DataFrame({
                    'Data Inicio': [processo.get('DataInicioRecebimentoProposta')],
                    'Data Fim': [processo.get('DataFimRecebimentoProposta')],
                    'CNPJ': [processo.get('Cnpj')],
                    'Órgão': [processo.get('Orgao')],
                    'Número': [processo.get('Numero')],
                    'Data Divulgação': [processo.get('Data')],
                    'Valor Estimado': [processo.get('ValorTotalEstimadoCompra')],
                    'Link': [processo.get('Link')]
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
    def gerarPlanilha(self, tipo_data, data_inicial, data_final, plataforma):
        global nome, filtros

        try:
            carregar_configuracoes()
        except:
            return "<p style='color:red;'>Arquivo de configuracao de conexão do banco de dados .json não localizado.</p>"

        filtros['data_inicial'] = data_inicial.strip()
        filtros['data_final'] = data_final.strip()
        filtros['tipo_data'] = tipo_data.strip()
        filtros['plataforma'] = plataforma.strip().lower()

        if tipo_data == "por_periodo" and filtros['data_inicial'] == "" and filtros['data_final'] == "":
            return "<p style='color:red;'>Deve ser informada a Data Inicial ou a Data Final " \
                           "ou marcar a opção para gerar Todos os Registros</p>"

        erro, nome = retornar_nome_planilha(plataforma, data_inicial, data_final)

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
    window = webview.create_window('Gerar Planilha', 'gerar_planilha_seguro.html', js_api=api, height=680)
    webview.start(func=js, args=window, debug=False)
