import webview
import sys
from pathlib import Path

from pncp_shared.config.controle_config import carregar_configuracoes
from pncp_planilha_desktop.services.excel_service import (
    verificar_existencia_planilha,
    retornar_nome_planilha,
    gerar_excel
)

#py -m PyInstaller src/pncp_planilha_desktop/gerar_planilha.py --onefile --noconsole --paths src --add-data "src/pncp_planilha_desktop/gerar_planilha.html;pncp_planilha_desktop" --add-data "src/pncp_bot_obra/config.json;pncp_bot_obra" --add-data "src/pncp_shared/metadata/metadados.db;pncp_shared/metadata"

def caminho_recurso(nome_arquivo):
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "pncp_planilha_desktop" / nome_arquivo

    return Path(__file__).resolve().parent / nome_arquivo


def js(window):
    pass

nome = ""
filtros = {}
window = None

class Api:
    def gerarPlanilha(self, tipo_data, data_inicial, data_final, plataforma, link_edital):
        global nome, filtros

        try:
           carregar_configuracoes(plataforma)
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


if __name__ == "__main__":
    api = Api()

    html_path = caminho_recurso("gerar_planilha.html")

    window = webview.create_window(
        "Gerar Planilha",
        str(html_path),
        js_api=api,
        height=680
    )

    webview.start(func=js, args=window, debug=False)
