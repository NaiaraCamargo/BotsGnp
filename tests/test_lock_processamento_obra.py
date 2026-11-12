import unittest
from contextlib import ExitStack, contextmanager, nullcontext
from threading import Lock
from unittest.mock import patch

from pncp_bot_obra.services import processamento_edital as obra


class LockProcessamentoObraTest(unittest.TestCase):
    def test_lock_protege_consulta_e_processamento_e_respeita_termos_e_destinos(self):
        casos = [(None, set(), True), ({'id': 123, 'termos': 'reforma'}, {'GNP'}, False),
                 ({'id': 123, 'termos': 'reforma'}, set(), True), ({'id': 123, 'termos': 'ponte'}, {'GNP'}, True)]
        for existente, destinos_processados, deve_processar in casos:
            with self.subTest(existente=existente, destinos=destinos_processados), ExitStack() as stack:
                estado = {'bloqueado': False}
                edital = {'Link': 'https://pncp.gov.br/app/editais/12345678901234/2026/1'}
                em_processamento = set()

                @contextmanager
                def bloquear(link):
                    estado['bloqueado'] = True
                    try:
                        yield True
                    finally:
                        estado['bloqueado'] = False

                def consultar(link):
                    self.assertTrue(estado['bloqueado'])
                    return existente

                def processar(*args):
                    self.assertTrue(estado['bloqueado'])
                    self.assertEqual(args[-1], existente['id'] if existente else None)
                    return edital, 0

                stack.enter_context(patch.object(obra, 'extrair_dados_edital', return_value=edital))
                stack.enter_context(patch.object(obra, 'validar_palavras', return_value=['reforma']))
                stack.enter_context(patch.object(obra, 'bloquear_processamento_edital', side_effect=bloquear))
                stack.enter_context(patch.object(obra, 'verificar_existencia_edital_new', side_effect=consultar))
                stack.enter_context(patch.object(obra, 'retornar_destinos_processados', return_value=destinos_processados))
                atualizar = stack.enter_context(patch.object(obra, 'atualizar_termos_edital'))
                processamento = stack.enter_context(patch.object(obra, 'processar_edital', side_effect=processar))
                filtros = {'banco': {'destinos': ['GNP']}}
                resultado = obra.processar_texto('texto', 'teste', None, 'url', 1, [], 10, False, filtros,
                                                 Lock(), em_processamento, 0, termo_busca='reforma')

                self.assertEqual(resultado, (edital if deve_processar else None, 0))
                self.assertEqual(processamento.call_count, int(deve_processar))
                self.assertEqual(atualizar.call_count, int(bool(existente and existente['termos'] == 'ponte')))
                self.assertFalse(estado['bloqueado'])
                self.assertEqual(em_processamento, set())

    def test_lock_ocupado_pula_consulta_e_processamento(self):
        em_processamento = set()
        with patch.object(obra, 'extrair_dados_edital', return_value={'Link': 'https://edital'}), \
             patch.object(obra, 'validar_palavras', return_value=[]), ExitStack() as stack:
            stack.enter_context(patch.object(obra, 'bloquear_processamento_edital', return_value=nullcontext(False)))
            consultar = stack.enter_context(patch.object(obra, 'verificar_existencia_edital_new'))
            processar = stack.enter_context(patch.object(obra, 'processar_edital'))
            resultado = obra.processar_texto('texto', 'teste', None, 'url', 1, [], 10, False, {'banco': {'destinos': ['GNP']}},
                                             Lock(), em_processamento, 0, termo_busca='reforma')

        self.assertEqual(resultado, (None, 0))
        consultar.assert_not_called()
        processar.assert_not_called()
        self.assertEqual(em_processamento, set())
