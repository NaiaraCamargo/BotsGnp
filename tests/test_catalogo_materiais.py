import unittest

from pncp_bot_material_escolar.services.catalogo_materiais import classificar_itens_catalogo, codigos_unicos_do_edital
from pncp_shared.api.api_edital import montar_itens_campos


class CatalogoMateriaisTest(unittest.TestCase):
    def test_classificacao_preserva_campos_comuns_sem_alterar_itens_originais(self):
        itens = montar_itens_campos('link', [{'numeroItem': 1, 'descricao': 'COLA EM BASTÃO', 'quantidade': 3,
                                             'valorUnitarioEstimado': 2, 'valorTotalEstimado': 6}])
        classificados = classificar_itens_catalogo(itens)
        self.assertEqual(classificados[0]['codigosCatalogo'], [6])
        self.assertTrue(classificados[0]['itemValidoCatalogo'])
        self.assertNotIn('codigosCatalogo', itens[0])
        for campo, valor in itens[0].items():
            self.assertEqual(classificados[0][campo], valor)

    def test_itens_fora_do_catalogo_ou_sem_descricao_nao_sao_validos(self):
        itens = [{'descricaoItem': 'Seguro predial'}, {'descricaoItem': None}]
        classificados = classificar_itens_catalogo(itens)
        self.assertTrue(all(not item['itemValidoCatalogo'] for item in classificados))
        self.assertEqual(codigos_unicos_do_edital(classificados), [])

    def test_codigos_do_edital_sao_unicos_e_ordenados(self):
        itens = [{'descricaoItem': 'Papel A4'}, {'descricaoItem': 'Grampo 26/6'}, {'descricaoItem': 'Papel sulfite'}]
        self.assertEqual(codigos_unicos_do_edital(classificar_itens_catalogo(itens)), [2, 15])
