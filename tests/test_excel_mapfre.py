import os
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from mapfre_downloader.services import excel_service as excel
from pncp_shared.config.controle_config import configuracoes


class ExcelMapfreTest(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.caminho = os.path.join(temporario.name, "reservas.xlsx")
        config = patch.dict(configuracoes, {"aba_excel": "COM DADOS", "salvar_planilha_a_cada": 10}, clear=True)
        config.start()
        self.addCleanup(config.stop)
        self.addCleanup(excel.fechar_planilha)
        wb = Workbook()
        ws = wb.active
        ws.title = "COM DADOS"
        ws.append(["RESERVA", "RAMO", "PRÊMIO", "PROCESSADO", "ÓRGÃO"])
        ws.append(["1", "seguro", 100, "OK", "anterior"])
        ws.append(["1", "seguro", 100, "", ""])
        ws.append(["2", "seguro", 100, "", ""])
        wb.save(self.caminho)
        wb.close()

    def test_leitura_preserva_linha_de_origem_ao_ignorar_processadas(self):
        with patch.object(excel, "carregar_premios_por_reserva", return_value={}):
            reservas = excel.ler_links_excel(self.caminho)
        self.assertEqual([(reserva["reserva"], reserva["linha_excel"]) for reserva in reservas], [("1", 3), ("2", 4)])

    def test_resultados_fora_de_ordem_atualizam_as_linhas_corretas(self):
        excel.atualizar_planilha(2, 1, "orgao-2", "link-2", self.caminho, "2", False, "falhou", linha_excel=4)
        excel.atualizar_planilha(3, 3, "orgao-1", "link-1", self.caminho, "1", True, "concluiu", linha_excel=3)
        excel.fechar_planilha()
        wb = load_workbook(self.caminho)
        self.addCleanup(wb.close)
        ws = wb["COM DADOS"]
        colunas = {celula.value: celula.column for celula in ws[1]}
        self.assertEqual(ws.cell(2, colunas["ÓRGÃO"]).value, "anterior")
        self.assertIsNone(ws.cell(2, colunas["Nº ARQUIVOS BAIXADOS"]).value)
        self.assertEqual(ws.cell(3, colunas["Nº ARQUIVOS BAIXADOS"]).value, 3)
        self.assertEqual(ws.cell(3, colunas["LINK RESERVA"]).value, "link-1")
        self.assertEqual(ws.cell(4, colunas["Nº ARQUIVOS BAIXADOS"]).value, 1)
        self.assertEqual(ws.cell(4, colunas["PROCESSADO"]).value, "ERRO")
        self.assertEqual(ws.cell(4, colunas["MENSAGEM DO BOT"]).value, "falhou")

    def test_rejeita_linha_de_outra_reserva(self):
        with self.assertRaisesRegex(ValueError, "nao corresponde"):
            excel.atualizar_planilha(1, 1, "", "", self.caminho, "1", True, "OK", linha_excel=4)


if __name__ == "__main__":
    unittest.main()
