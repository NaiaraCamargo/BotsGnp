import copy
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import requests

from pncp_bot_material_escolar.services import processamento_edital as material
from pncp_bot_obra.services import processamento_edital as obra
from pncp_bot_seguro.services import processamento_edital as seguro
from pncp_shared.api import compras_pncp
from pncp_shared.utils.edital_texto import extrair_dados_edital


TEXTO = (Path(__file__).parent / 'fixtures/edital_listagem.txt').read_text(encoding='utf-8')


class FluxoComplementosApiTest(unittest.TestCase):
    def executar_fluxo(self, modulo, destino=None, falha=False, id_busca=None, existente=None):
        edital = extrair_dados_edital(TEXTO, incluir_homologado=modulo is seguro)
        edital['Uf'] = 'RS'
        eventos, enviados, gravados, erros = [], [], [], []
        itens = [{'numeroItem': 1, 'descricao': 'Papel A4', 'quantidade': 10, 'valorTotalEstimado': 50}]

        def quantidade(*args, **kwargs):
            eventos.append('quantidade')
            return 1

        def requisicao(method, url, **kwargs):
            from unittest.mock import Mock
            resposta = Mock()
            if url.endswith('/itens'):
                eventos.append('itens')
                resposta.json.return_value = itens
            else:
                eventos.append('consulta')
                self.assertTrue(url.startswith(compras_pncp.CONSULTA))
                if falha:
                    raise requests.Timeout('consulta indisponivel')
                resposta.json.return_value = {'linkSistemaOrigem': 'https://compras.gov.br/1', 'valorTotalHomologado': 123.45}
            return resposta

        def enviar(dados, chats, **kwargs):
            eventos.append('envio')
            enviados.append(copy.deepcopy(dados))
            return list(chats)

        def gravar(dados, *args):
            eventos.append('gravacao')
            gravados.append(copy.deepcopy(dados))
            return existente or 'processo'

        with ExitStack() as stack:
            stack.enter_context(patch.object(compras_pncp, 'get_int', side_effect=quantidade))
            stack.enter_context(patch.object(compras_pncp, 'requisicao_pncp', side_effect=requisicao))
            stack.enter_context(patch.object(modulo, 'enviar_mensagem', side_effect=enviar))
            stack.enter_context(patch.object(modulo, 'obter_pastas_download', return_value=('pasta', 'comprimidos')))
            stack.enter_context(patch.object(modulo, 'buscar_arquivos', return_value=[]))
            stack.enter_context(patch.object(modulo, 'gravar_novo_processo', side_effect=gravar))
            if modulo is obra:
                stack.enter_context(patch.object(obra, 'calcular_destinos_aprovados', return_value={destino}))
                stack.enter_context(patch.object(obra, 'retornar_destinos_enviados', return_value=set()))
                registrar = stack.enter_context(patch.object(obra, 'registrar_resultado_envio_bot', side_effect=lambda *args: eventos.append('historico')))
                bool_envio = stack.enter_context(patch.object(obra, 'gravar_processo_botbool_envio'))
                destinatarios = [{'id_telegram': 'canal', 'codigo_destino': destino}]
                resultado = modulo.processar_edital(edital, ['canal'], 0, ['Reforma'], {}, 'obra', erros, {destino}, destinatarios, existente)
                registrar.assert_called_once_with(existente or 'processo', destino, 'enviado', '')
                self.assertGreater(eventos.index('historico'), eventos.index('gravacao'))
                self.assertEqual(bool_envio.call_count, int(destino == 'BOOL'))
            elif modulo is seguro:
                stack.enter_context(patch.object(seguro, 'registrar_notificacoes_busca'))
                resultado = modulo.processar_edital(edital, ['canal'], 0, ['Reforma'], {}, 'seguro', erros, id_busca, existente, [])
            else:
                resultado = modulo.processar_edital(edital, ['canal'], 0, ['Reforma'], {}, 'material', erros)

        self.assertIs(resultado[0], edital)
        self.assertEqual(resultado[1], 0)
        self.assertEqual(eventos[:4], ['quantidade', 'itens', 'envio', 'consulta'])
        self.assertEqual(len(enviados), 1)
        self.assertNotIn('LinkBotao', enviados[0])
        self.assertIsNone(enviados[0].get('ValorTotalHomologado'))
        self.assertEqual(edital['QuantidadeItens'], 1)
        self.assertEqual(edital['itens_dados'][0]['descricaoItem'], 'Papel A4')
        if falha:
            self.assertEqual(edital, enviados[0])
            self.assertEqual(erros[0]['tipo_erro'], 'TIMEOUT_GET_JSON')
            self.assertEqual(erros[0]['link_origem'], edital['Link'])
        else:
            self.assertEqual(edital['LinkBotao'], 'https://compras.gov.br/1')
            self.assertEqual(edital['ValorTotalHomologado'], 'R$ 123,45')
            self.assertEqual(erros, [])
        if existente and modulo is seguro:
            self.assertEqual(gravados, [])
        else:
            self.assertEqual(gravados, [edital])
            self.assertGreater(eventos.index('gravacao'), eventos.index('consulta'))

    def test_todos_os_bots_enviam_antes_de_consultar_e_gravar_inclusive_com_timeout(self):
        for modulo, destino in ((obra, 'GNP'), (obra, 'BOOL'), (obra, 'EDIT'), (material, None), (seguro, None)):
            for falha in (False, True):
                with self.subTest(bot=modulo.__name__, destino=destino, falha=falha):
                    self.executar_fluxo(modulo, destino, falha)

    def test_busca_adicional_seguro_mantem_registro_de_notificacao(self):
        for existente in (None, 'processo-existente'):
            with self.subTest(existente=existente):
                self.executar_fluxo(seguro, id_busca=10, existente=existente)

    def test_obras_nao_reenvia_destino_ja_notificado(self):
        edital = extrair_dados_edital(TEXTO)
        with ExitStack() as stack:
            stack.enter_context(patch.object(obra, 'tentar_buscar_itens', return_value=(0, [], False)))
            stack.enter_context(patch.object(obra, 'calcular_destinos_aprovados', return_value={'GNP', 'BOOL'}))
            consultar = stack.enter_context(patch.object(obra, 'retornar_destinos_enviados', return_value={'GNP'}))
            enviar = stack.enter_context(patch.object(obra, 'enviar_para_destinos', return_value={'BOOL'}))
            stack.enter_context(patch.object(obra, 'complementar_edital'))
            stack.enter_context(patch.object(obra, 'gravar_novo_processo', return_value='existente'))
            stack.enter_context(patch.object(obra, 'gravar_processo_botbool_envio'))
            obra.processar_edital(edital, [], 0, ['Reforma'], {}, 'obra', [], {'GNP', 'BOOL'}, [], 'existente')
        consultar.assert_called_once_with('existente')
        self.assertEqual(enviar.call_args.args[2], {'BOOL'})

    def test_itens_incompletos_impedem_envio_consulta_e_gravacao(self):
        for modulo in (obra, seguro, material):
            with self.subTest(bot=modulo.__name__), ExitStack() as stack:
                stack.enter_context(patch.object(modulo, 'tentar_buscar_itens', return_value=(None, [], False)))
                enviar = stack.enter_context(patch.object(modulo, 'enviar_mensagem'))
                complementar = stack.enter_context(patch.object(modulo, 'complementar_edital'))
                gravar = stack.enter_context(patch.object(modulo, 'gravar_novo_processo'))
                argumentos = ({'GNP'}, []) if modulo is obra else ()
                resultado = modulo.processar_edital({'Link': 'https://pncp.gov.br/app/editais/35250517000113/2026/11'}, [], 0,
                                                    ['Reforma'], {}, 'teste', [], *argumentos)
                self.assertEqual(resultado, (None, 0))
                enviar.assert_not_called()
                complementar.assert_not_called()
                gravar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
