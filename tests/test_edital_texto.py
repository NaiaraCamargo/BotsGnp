import unittest
from pathlib import Path

from pncp_shared.utils.edital_texto import TextoEditalIncompleto, extrair_dados_edital, normalizar_valor_monetario
from pncp_shared.utils.funcoespncp import formatar_data_hora_string


TEXTO = (Path(__file__).parent / 'fixtures/edital_listagem.txt').read_text(encoding='utf-8')


class EditalTextoTest(unittest.TestCase):
    def test_extrai_exemplo_sem_confundir_numero_sequencial_e_datas(self):
        dados = extrair_dados_edital(TEXTO)
        self.assertEqual(dados['Numero'], '12/2026')
        self.assertEqual(dados['NumeroAux'], '12')
        self.assertEqual(dados['Link'], 'https://pncp.gov.br/app/editais/35250517000113/2026/11')
        self.assertEqual(dados['Data'], '16/09/2026')
        self.assertEqual(dados['DataFim'], '01/10/2026')
        self.assertEqual(dados['HoraFim'], '09:00')
        self.assertEqual(dados['DataInicioRecebimentoProposta'], '17/09/2026 09:00')
        self.assertEqual(dados['DataFimRecebimentoProposta'], '01/10/2026 09:00')
        self.assertEqual(dados['ValorTotalEstimadoCompra'], 'R$ 3.014.398,23')
        self.assertEqual(dados['FontesOrcamentarias'], 'Municipal')
        self.assertEqual(dados['fonte_plataforma'], 'Compras.gov.br')

    def test_nao_confunde_orgao_e_unidade_com_subrogados(self):
        dados = extrair_dados_edital(TEXTO)
        self.assertTrue(dados['Orgao'].startswith('UNIDADE EXEC.'))
        self.assertEqual(dados['Cnpj'], '35250517000113')
        self.assertEqual(dados['CodigoUnidadeCompradora'], '928325')
        self.assertEqual(dados['Municipio'], 'Parauapebas/PA')
        self.assertEqual(dados['Uf'], 'PA')

    def test_objeto_multilinha_preserva_apostrofo_e_dois_pontos(self):
        texto = TEXTO.replace('Objeto: Registro', "Objeto: Reforma d'água:\nsegunda etapa\nRegistro")
        dados = extrair_dados_edital(texto)
        self.assertTrue(dados['Descricao'].startswith("Reforma d'agua:\nsegunda etapa\nRegistro"))
        self.assertNotIn('Valor Total', dados['Descricao'])

    def test_zero_segue_regra_existente_de_sigilo(self):
        for valor in (0, 0.0, '0', '0,00', 'R$ 0,00', 'R$ 0.000,00'):
            with self.subTest(valor=valor):
                self.assertEqual(normalizar_valor_monetario(valor), 'SIGILOSO')
        self.assertIsNone(normalizar_valor_monetario('Não informado'))
        self.assertEqual(normalizar_valor_monetario('Sigiloso'), 'SIGILOSO')
        with self.assertRaises(TextoEditalIncompleto):
            normalizar_valor_monetario('valor corrompido')

    def test_extracao_mantem_estimado_sigiloso_e_homologado_ausente(self):
        for incluir_homologado in (False, True):
            for valor in ('R$ 0,00', 'Não informado', ''):
                with self.subTest(incluir_homologado=incluir_homologado, valor=valor):
                    dados = extrair_dados_edital(TEXTO.replace('R$ 3.014.398,23', valor), incluir_homologado=incluir_homologado)
                    self.assertEqual(dados['ValorTotalEstimadoCompra'], 'SIGILOSO')
                    self.assertIsNone(dados.get('ValorTotalHomologado'))

    def test_extracao_mantem_homologado_zero_como_sigiloso(self):
        dados = extrair_dados_edital(TEXTO + '\nValor Total Homologado: R$ 0,00', incluir_homologado=True)
        self.assertEqual(dados['ValorTotalHomologado'], 'SIGILOSO')

    def test_estimado_zero_mantem_aprovacao_do_bool_por_sigilo(self):
        from pncp_bot_obra.services.roteamento_bots import calcular_destinos_aprovados

        dados = extrair_dados_edital(TEXTO.replace('R$ 3.014.398,23', 'R$ 0,00'))
        self.assertEqual(calcular_destinos_aprovados(dados, {'BOOL'}), {'BOOL'})

    def test_texto_incompleto_e_link_divergente_sao_rejeitados(self):
        with self.assertRaises(TextoEditalIncompleto):
            extrair_dados_edital(TEXTO.replace('Id contratação PNCP:', 'Identificador desconhecido:'))
        with self.assertRaises(TextoEditalIncompleto):
            extrair_dados_edital(TEXTO, 'https://pncp.gov.br/app/editais/35250517000113/2026/12')

    def test_campos_invalidos_geram_erro_tratado_pelos_bots(self):
        alteracoes = [('35250517000113-1-000011/2026', 'identificador invalido'),
                      ('Edital nº 12/2026', 'Edital sem numero'), ('Parauapebas/PA', 'localidade invalida')]
        for original, substituto in alteracoes:
            with self.subTest(original=original), self.assertRaises(TextoEditalIncompleto):
                extrair_dados_edital(TEXTO.replace(original, substituto))

    def test_datas_com_horario_ficam_sem_segundos(self):
        for valor in ('01/10/2026 09:00', '01/10/2026 09:00:00', '2026-10-01T09:00:00'):
            with self.subTest(valor=valor):
                self.assertEqual(formatar_data_hora_string(valor, incluir_segundos=False), '01/10/2026 09:00')
        self.assertEqual(formatar_data_hora_string('01/10/2026 09:00:35', incluir_segundos=False), '01/10/2026 09:00')

    def test_datas_ausentes_e_sem_horario_nao_inventam_informacao(self):
        for valor in (None, '', 'Não informado', 'Não se aplica', '-'):
            with self.subTest(valor=valor):
                self.assertEqual(formatar_data_hora_string(valor, incluir_segundos=False), '')
        self.assertEqual(formatar_data_hora_string('01/10/2026', incluir_segundos=False), '01/10/2026')

    def test_data_invalida_preserva_conteudo_sem_interromper_extracao(self):
        texto = TEXTO.replace('16/09/2026', 'data desconhecida').replace('01/10/2026 09:00', 'prazo desconhecido')
        dados = extrair_dados_edital(texto)
        self.assertEqual(dados['Data'], formatar_data_hora_string('data desconhecida'))
        self.assertEqual(dados['DataFimRecebimentoProposta'], 'prazo desconhecido')
        self.assertIsNone(dados['DataFim'])
        self.assertIsNone(dados['HoraFim'])

    def test_separacao_da_data_fim_mantem_hora_sem_segundos(self):
        dados = extrair_dados_edital(TEXTO.replace('01/10/2026 09:00', '01/10/2026 09:00:35'))
        self.assertEqual(dados['DataFimRecebimentoProposta'], '01/10/2026 09:00')
        self.assertEqual((dados['DataFim'], dados['HoraFim']), ('01/10/2026', '09:00'))

    def test_aceita_modalidade_com_rotulo_antigo_e_aviso(self):
        texto = TEXTO.replace('Edital nº', 'Aviso de Contratação Direta nº').replace('Modalidade de Contratação:', 'Modalidade da Contratação:')
        self.assertEqual(extrair_dados_edital(texto)['Licitacao'], 'Pregão - Eletrônico')

    def test_nao_inventa_horario_ou_valor_homologado(self):
        dados = extrair_dados_edital(TEXTO.replace('01/10/2026 09:00', '01/10/2026'), incluir_homologado=True)
        self.assertIsNone(dados['HoraFim'])
        self.assertIsNone(dados['ValorTotalHomologado'])
        self.assertIsNone(dados.get('LinkBotao'))

    def test_extracao_ja_formata_descricao_e_destaca_uma_vez(self):
        texto = TEXTO + '\nValor Total Homologado: R$ 900.000,00'
        campos = extrair_dados_edital(texto, palavras_destacadas=['Reforma', 'Reforma do Parque'])
        self.assertIn('<b>Reforma do Parque</b>', campos['Descricao'])
        self.assertNotIn('<b><b>', campos['Descricao'])
        self.assertIn('Registro de Precos', campos['Descricao'])
        self.assertNotIn('QuantidadeItens', campos)
        self.assertNotIn('ValorTotalHomologado', campos)
        self.assertEqual(extrair_dados_edital(texto, incluir_homologado=True)['ValorTotalHomologado'], 'R$ 900.000,00')

    def test_descricao_preserva_limpeza_limites_e_destaque_sem_diferenciar_maiusculas(self):
        texto = TEXTO.replace('Objeto: Registro', 'Objeto: REFORMA reformar reforma d’água; Registro')
        dados = extrair_dados_edital(texto, palavras_destacadas=['reforma', 'REFORMA', 'reforma'])
        self.assertTrue(dados['Descricao'].startswith('<b>REFORMA</b> reformar <b>reforma</b> dagua; Registro'))
        self.assertNotIn('<b><b>', dados['Descricao'])
