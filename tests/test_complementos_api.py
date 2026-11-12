import copy
import unittest
from unittest.mock import Mock, patch

import requests

from pncp_shared.api import compras_pncp


LINK = 'https://pncp.gov.br/app/editais/35250517000113/2026/11'
URL = f'{compras_pncp.CONSULTA}/orgaos/35250517000113/compras/2026/11'


class ComplementosApiTest(unittest.TestCase):
    def complementar(self, edital, erros):
        return compras_pncp.complementar_edital(edital, '35250517000113', '2026', '11', erros)

    def test_preenche_campos_ausentes_e_preserva_texto_e_itens(self):
        edital = {'Link': LINK, 'Descricao': '<b>Objeto original</b>', 'ValorTotalEstimadoCompra': 'SIGILOSO',
                  'QuantidadeItens': 0, 'itens_dados': [], 'Data': '01/01/2026', 'ModoDeDisputa': '', 'LinkBotao': '  '}
        compra = {'linkSistemaOrigem': 'https://compras.gov.br/1', 'valorTotalHomologado': 123456.78,
                  'objetoCompra': 'Objeto diferente', 'valorTotalEstimado': 999, 'dataPublicacaoPncp': 'data ignorada',
                  'modoDisputaNome': 'Aberto', 'dataEncerramentoProposta': '2026-10-01T09:30:00.000-03:00',
                  'numeroCompra': '12', 'anoCompra': 2026, 'orgaoEntidade': {'razaoSocial': 'Prefeitura', 'cnpj': '35250517000113'},
                  'unidadeOrgao': {'municipioNome': 'Porto Alegre', 'ufSigla': 'RS', 'codigoUnidade': '123'}}
        itens = edital['itens_dados']
        with patch.object(compras_pncp, 'get_json', return_value=compra) as get_json:
            resultado = self.complementar(edital, [])
        self.assertIs(resultado, edital)
        self.assertEqual(edital['Descricao'], '<b>Objeto original</b>')
        self.assertEqual(edital['ValorTotalEstimadoCompra'], 'SIGILOSO')
        self.assertEqual(edital['QuantidadeItens'], 0)
        self.assertIs(edital['itens_dados'], itens)
        self.assertEqual(edital['Data'], '01/01/2026')
        self.assertEqual(edital['Numero'], '12/2026')
        self.assertEqual(edital['Municipio'], 'Porto Alegre/RS')
        self.assertEqual(edital['ModoDeDisputa'], 'Aberto')
        self.assertEqual(edital['DataFimRecebimentoProposta'], '01/10/2026 09:30:00')
        self.assertEqual((edital['DataFim'], edital['HoraFim']), ('01/10/2026', '09:30'))
        self.assertEqual(edital['LinkBotao'], compra['linkSistemaOrigem'])
        self.assertEqual(edital['ValorTotalHomologado'], 'R$ 123.456,78')
        self.assertEqual(get_json.call_args.args, (URL,))
        self.assertEqual(get_json.call_args.kwargs['link_origem'], LINK)

    def test_homologado_zero_e_preservacao_de_valor_existente(self):
        for original, esperado in ((None, 'SIGILOSO'), ('R$ 20,00', 'R$ 20,00'), (0, 0)):
            with self.subTest(original=original), patch.object(compras_pncp, 'get_json', return_value={'valorTotalHomologado': 0}):
                edital = {'Link': LINK, 'ValorTotalHomologado': original}
                self.complementar(edital, [])
                self.assertEqual(edital['ValorTotalHomologado'], esperado)

    def test_valores_nulos_nao_sao_convertidos_em_sigilosos(self):
        with patch.object(compras_pncp, 'get_json', return_value={'valorTotalHomologado': None, 'valorTotalEstimado': None}):
            edital = {'Link': LINK}
            self.complementar(edital, [])
        self.assertEqual(edital, {'Link': LINK})

    def test_resposta_invalida_preserva_edital_e_registra_url(self):
        for resposta in (None, [], {}, {'valorTotalHomologado': 'invalido'}, {'dataAberturaProposta': 'invalida'}):
            with self.subTest(resposta=resposta), patch.object(compras_pncp, 'get_json', return_value=resposta):
                edital = {'Link': LINK, 'itens_dados': [{'numeroItem': 1}]}
                original, erros = copy.deepcopy(edital), []
                self.assertIs(self.complementar(edital, erros), edital)
                self.assertEqual(edital, original)
                self.assertEqual(len(erros), 1)
                self.assertEqual(erros[0]['url'], URL)
                self.assertEqual(erros[0]['link_origem'], LINK)
                self.assertEqual(erros[0]['tipo_erro'], 'COMPLEMENTOS_EDITAL_INVALIDOS')

    def test_timeout_http_e_json_invalido_registram_erro_sem_perder_itens(self):
        resposta_http = Mock(status_code=503)
        falhas = [(requests.Timeout('timeout'), None, 'TIMEOUT_GET_JSON'),
                  (requests.HTTPError('503', response=resposta_http), None, 'HTTP_ERROR_GET_JSON_503'),
                  (None, ValueError('json invalido'), 'JSON_INVALIDO')]
        for falha_http, falha_json, tipo in falhas:
            with self.subTest(tipo=tipo):
                resposta = Mock()
                resposta.raise_for_status.side_effect = falha_http
                resposta.json.side_effect = falha_json
                edital, erros = {'Link': LINK, 'itens_dados': [{'numeroItem': 1}]}, []
                original = copy.deepcopy(edital)
                with patch.object(compras_pncp, 'requisicao_pncp', return_value=resposta):
                    self.complementar(edital, erros)
                self.assertEqual(edital, original)
                self.assertEqual(len(erros), 1)
                self.assertEqual(erros[0]['tipo_erro'], tipo)
                self.assertEqual(erros[0]['url'], URL)


if __name__ == '__main__':
    unittest.main()
