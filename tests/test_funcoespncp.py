import unittest

from pncp_shared.utils.funcoespncp import destacar_palavras, formatar_data_hora_string, separar_data_hora


class FuncoesPncpTest(unittest.TestCase):
    def test_formatacao_antiga_de_iso_continua_disponivel_por_padrao(self):
        self.assertEqual(formatar_data_hora_string('2026-10-01T09:00:35'), '01/10/2026 09:00:35')
        self.assertEqual(formatar_data_hora_string('data invalida'), 'data invalida')

    def test_separacao_aceita_iso_e_texto_sem_adicionar_horario(self):
        for valor in ('2026-10-01T09:00:35', '2026-10-01T09:00:35-03:00', '01/10/2026 09:00:35', '01/10/2026 09:00'):
            with self.subTest(valor=valor):
                self.assertEqual(separar_data_hora(valor), ('01/10/2026', '09:00'))
        for valor in ('2026-10-01', '01/10/2026'):
            with self.subTest(valor=valor):
                self.assertEqual(separar_data_hora(valor), ('01/10/2026', None))

    def test_separacao_nao_inventa_datas_para_campos_ausentes_ou_invalidos(self):
        for valor in (None, '', 'Não informado', 'prazo desconhecido', '31/02/2026 09:00'):
            with self.subTest(valor=valor):
                self.assertEqual(separar_data_hora(valor), (None, None))

    def test_destaque_compartilhado_preserva_texto_sem_palavras_e_evitar_sobreposicao(self):
        self.assertEqual(destacar_palavras('Reforma do parque e REFORMA', ['reforma', 'Reforma do parque']), '<b>Reforma do parque</b> e <b>REFORMA</b>')
        self.assertEqual(destacar_palavras('Reforma do parque', []), 'Reforma do parque')


if __name__ == '__main__':
    unittest.main()
