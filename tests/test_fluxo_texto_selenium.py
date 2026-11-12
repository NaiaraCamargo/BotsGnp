import unittest
from contextlib import ExitStack, nullcontext
from pathlib import Path
from threading import Lock
from unittest.mock import patch

from pncp_bot_material_escolar.services import processamento_edital as material
from pncp_bot_obra.services import processamento_edital as obra
from pncp_bot_seguro.services import processamento_edital as seguro
from pncp_shared.api import compras_pncp
from pncp_shared.utils import edital_texto
from pncp_shared.utils.validadores_pncp import validar_modalidade_obras, validar_palavras, validar_texto_seguro
from test_complementos_edital import DriverFake


TEXTO = (Path(__file__).parent / 'fixtures/edital_listagem.txt').read_text(encoding='utf-8')


class FluxoTextoSeleniumTest(unittest.TestCase):
    def test_tres_bots_gravam_dados_do_texto_e_complementos_sem_get_compra(self):
        for modulo, destinos in ((obra, {'GNP'}), (obra, set()), (material, set()), (seguro, set())):
            with self.subTest(bot=modulo.__name__, destinos=destinos), ExitStack() as stack:
                driver = DriverFake()
                def verificar_existencia(link):
                    self.assertEqual([url for _, url in driver.navegacoes], [link])
                    self.assertEqual(driver.current_window_handle, 'listagem')
                    return None
                itens_api = [{'numeroItem': 1, 'descricao': 'Papel A4', 'quantidade': 10, 'valorUnitarioEstimado': 5, 'valorTotalEstimado': 50}]
                stack.enter_context(patch.object(compras_pncp, 'get_int', return_value=1))
                get_json = stack.enter_context(patch.object(compras_pncp, 'get_json', return_value=itens_api))
                stack.enter_context(patch.object(edital_texto, 'executar_navegacao_pncp', side_effect=lambda operacao: operacao()))
                stack.enter_context(patch.object(modulo, 'obter_pastas_download', return_value=('pasta', 'comprimidos')))
                stack.enter_context(patch.object(modulo, 'buscar_arquivos', return_value=[]))
                stack.enter_context(patch.object(modulo, 'enviar_mensagem', return_value=[]))
                stack.enter_context(patch.object(modulo, 'verificar_existencia_edital_new', side_effect=verificar_existencia))
                gravar = stack.enter_context(patch.object(modulo, 'gravar_novo_processo', return_value=123))
                if modulo is obra:
                    stack.enter_context(patch.object(obra, 'bloquear_processamento_edital', return_value=nullcontext(True)))
                    stack.enter_context(patch.object(obra, 'calcular_destinos_aprovados', return_value=destinos))
                    stack.enter_context(patch.object(obra, 'retornar_destinos_enviados', return_value=set()))
                    stack.enter_context(patch.object(obra, 'registrar_resultado_envio_bot'))
                    enviar = stack.enter_context(patch.object(obra, 'enviar_para_destinos', return_value=set()))
                filtros = {'banco': {'palavraschave': {'reforma': []}, 'destinos': ['GNP']}}
                em_processamento = set()
                edital, erros = modulo.processar_texto(TEXTO, 'teste', driver, 'https://pncp.gov.br/app/editais', 1, [], 10, False,
                                                        filtros, Lock(), em_processamento, 0, lista_erros_api=[])
                self.assertIsNotNone(edital)
                self.assertEqual(erros, 0)
                self.assertEqual(edital['Numero'], '12/2026')
                self.assertEqual(edital['Municipio'], 'Parauapebas/PA')
                self.assertEqual(edital['LinkBotao'], 'https://compras.gov.br/compra/1')
                self.assertEqual(edital['ValorTotalEstimadoCompra'], 'R$ 3.014.398,23')
                self.assertEqual(edital['QuantidadeItens'], 1)
                self.assertEqual(edital['itens_dados'][0]['descricaoItem'], 'Papel A4')
                self.assertEqual(edital['itens_dados'][0]['valorTotalItem'], 50)
                if modulo is material:
                    self.assertEqual(edital['codigos_catalogo'], [15])
                    self.assertEqual(edital['itens_validos'], edital['itens_dados'])
                else:
                    self.assertNotIn('codigosCatalogo', edital['itens_dados'][0])
                self.assertEqual(edital['fonte_plataforma'], 'Compras.gov.br')
                self.assertIn('<b>Reforma</b>', edital['Descricao'])
                self.assertEqual(em_processamento, set())
                if modulo is seguro:
                    self.assertEqual(edital['ValorTotalHomologado'], 'R$ 123.456,78')
                gravar.assert_called_once()
                self.assertIs(gravar.call_args.args[0], edital)
                get_json.assert_called_once()
                self.assertTrue(get_json.call_args.args[0].endswith('/compras/2026/11/itens'))
                self.assertEqual(driver.current_window_handle, 'listagem')
                if modulo is obra:
                    self.assertEqual(enviar.call_args.args[2], destinos)

    def test_filtros_leem_objeto_multilinha_sem_incluir_outros_campos(self):
        texto = 'Objeto: Aquisicao\nde seguro\nFonte/Plataforma: reforma'
        filtros = {'banco': {'palavraschave': {'seguro': [], 'reforma': []}}}
        self.assertEqual(validar_palavras(texto=texto, filtros_base=filtros), ['seguro'])
        self.assertEqual(validar_texto_seguro(texto, filtros), ['seguro'])

    def test_modalidade_aceita_os_dois_rotulos(self):
        self.assertTrue(validar_modalidade_obras(TEXTO))
        self.assertTrue(validar_modalidade_obras(TEXTO.replace('Modalidade de Contratação:', 'Modalidade da Contratação:')))
