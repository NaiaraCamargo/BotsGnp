import unittest

from pncp_planilha_desktop.utils.planilha_utils import format_data, limpar_nome_arquivo, plataforma_tem_itens


class PlanilhaUtilsTest(unittest.TestCase):
    def test_identifica_plataformas_com_itens(self):
        self.assertTrue(plataforma_tem_itens("obra"))
        self.assertFalse(plataforma_tem_itens("seguro"))

    def test_formata_data_para_nome_da_planilha(self):
        self.assertEqual(format_data("2026-08-06"), "06-08-2026")

    def test_remove_caracteres_invalidos_do_nome(self):
        self.assertEqual(limpar_nome_arquivo('edital:01/2026?'), "edital_01_2026_")


if __name__ == "__main__":
    unittest.main()
