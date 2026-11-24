import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from pncp_shared.utils import edital_texto as modulo


IDENTIFICADOR = '35250517000113-1-000011/2026'
LINK = 'https://pncp.gov.br/app/editais/35250517000113/2026/11'


class DriverFake:
    def __init__(self):
        self.current_window_handle = 'listagem'
        self.window_handles = ['listagem']
        self.timeouts = SimpleNamespace(page_load=60)
        self.switch_to = SimpleNamespace(window=self.selecionar, new_window=self.nova_aba)
        self.texto = f'Id contratação PNCP: {IDENTIFICADOR}\nObjeto: seguro\nVALOR TOTAL HOMOLOGADO\nR$ 123.456,78'
        self.urls = {'listagem': 'https://pncp.gov.br/app/editais'}
        self.url_externa = 'https://compras.gov.br/compra/1'
        self.abrir_nova_aba = True
        self.botao = Mock(spec=WebElement)
        self.botao.is_displayed.return_value = True
        self.botao.is_enabled.return_value = True
        self.botao.click.side_effect = self.clicar_botao
        self.localizadores = []
        self.navegacoes = []

    @property
    def current_url(self):
        return self.urls[self.current_window_handle]

    def clicar_botao(self):
        if self.abrir_nova_aba:
            self.nova_aba('tab')
        self.urls[self.current_window_handle] = self.url_externa

    def close(self):
        self.window_handles.remove(self.current_window_handle)
        del self.urls[self.current_window_handle]

    def selecionar(self, handle):
        self.current_window_handle = handle

    def nova_aba(self, tipo):
        handle = f'aba{len(self.window_handles)}'
        self.window_handles.append(handle)
        self.urls[handle] = 'about:blank'
        self.selecionar(handle)

    def set_page_load_timeout(self, timeout):
        self.timeouts.page_load = timeout

    def get(self, url):
        self.navegacoes.append((self.current_window_handle, url))
        self.urls[self.current_window_handle] = url

    def find_element(self, *args):
        if args != (By.XPATH, '//div[@id="main-content"]/pncp-item-detail/div'):
            raise AssertionError(f'Localizador inesperado: {args}')
        elemento = Mock(spec=WebElement, text=self.texto)
        elemento.find_elements.side_effect = self.find_elements
        return elemento

    def find_elements(self, *args):
        self.localizadores.append(args)
        return [self.botao] if args == (By.XPATH, './/div[1]/div[2]/div/button') and self.botao is not None else []

    def execute_script(self, script, *args):
        if not script.startswith('window.open'):
            raise AssertionError('Nao deve aguardar document.readyState')
        original = self.current_window_handle
        self.nova_aba('tab')
        self.get(args[0])
        self.selecionar(original)


class NovaPaginaTest(unittest.TestCase):
    def setUp(self):
        self.navegacao = patch.object(modulo, 'executar_navegacao_pncp', side_effect=lambda operacao: operacao())
        self.navegacao.start()
        self.addCleanup(self.navegacao.stop)

    def test_abre_detalhe_captura_url_e_restaura_listagem(self):
        driver = DriverFake()
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, incluir_homologado=True)
        self.assertEqual(resultado, {'LinkBotao': driver.url_externa, 'ValorTotalHomologado': 'R$ 123.456,78'})
        self.assertEqual(driver.window_handles, ['listagem'])
        self.assertEqual(driver.current_window_handle, 'listagem')
        driver.botao.click.assert_called_once()
        self.assertEqual(driver.localizadores, [(By.XPATH, './/div[1]/div[2]/div/button')])

    def test_nao_exige_identificador_objeto_ou_estado_global_da_pagina(self):
        driver = DriverFake()
        driver.texto = 'Detalhes da compra'
        self.assertEqual(modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}), {'LinkBotao': driver.url_externa})

    def test_captura_popup_preserva_abas_existentes_e_volta_a_aba_correta(self):
        driver = DriverFake()
        driver.nova_aba('tab')
        driver.urls[driver.current_window_handle] = 'https://pncp.gov.br/app/editais?pagina=2'
        original, anteriores = driver.current_window_handle, set(driver.window_handles)
        driver.abrir_nova_aba = True
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK})
        self.assertEqual(resultado['LinkBotao'], driver.url_externa)
        self.assertEqual(set(driver.window_handles), anteriores)
        self.assertEqual(driver.current_window_handle, original)

    def test_falha_ao_abrir_nao_fecha_listagem(self):
        driver = DriverFake()
        driver.execute_script = Mock(side_effect=WebDriverException('Nao abriu a aba'))
        erros = []
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, lista_erros_api=erros)
        self.assertEqual(resultado, {})
        self.assertEqual(driver.window_handles, ['listagem'])
        self.assertEqual(driver.current_window_handle, 'listagem')
        self.assertEqual(erros[0]['tipo_erro'], 'COMPLEMENTOS_SELENIUM')

    def test_sem_campos_opcionais_nao_cria_chave_none(self):
        driver = DriverFake()
        driver.botao = None
        driver.texto = 'Valor total estimado: R$ 900,00'
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, incluir_homologado=True)
        self.assertEqual(resultado, {})
        self.assertNotIn(None, resultado)

    def test_popup_em_branco_preserva_homologado_e_fecha_as_abas_criadas(self):
        driver = DriverFake()
        driver.abrir_nova_aba = True
        driver.url_externa = 'about:blank'
        erros = []
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, incluir_homologado=True, lista_erros_api=erros, timeout=0)
        self.assertEqual(resultado, {'ValorTotalHomologado': 'R$ 123.456,78'})
        self.assertEqual(erros, [])
        self.assertEqual(driver.window_handles, ['listagem'])
        self.assertEqual(driver.current_window_handle, 'listagem')

    def test_clique_sem_redirecionamento_nao_captura_url_do_pncp(self):
        driver = DriverFake()
        driver.botao.click.side_effect = None
        erros = []
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, lista_erros_api=erros, timeout=0)
        self.assertEqual(resultado, {})
        self.assertEqual(len(erros), 1)
        self.assertEqual(driver.window_handles, ['listagem'])

    def test_timeout_do_clique_preserva_homologado_e_restaura_listagem(self):
        driver = DriverFake()
        def clicar():
            driver.clicar_botao()
            raise TimeoutException('Destino externo demorou para carregar')
        driver.botao.click.side_effect = clicar
        erros = []
        resultado = modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, incluir_homologado=True, lista_erros_api=erros)
        self.assertEqual(resultado, {'ValorTotalHomologado': 'R$ 123.456,78'})
        self.assertEqual(len(erros), 1)
        self.assertEqual(driver.window_handles, ['listagem'])
        self.assertEqual(driver.current_window_handle, 'listagem')

    def test_campos_ja_preenchidos_nao_abrem_pagina(self):
        driver = DriverFake()
        edital = {'LinkBotao': driver.url_externa, 'ValorTotalHomologado': 'R$ 0,00'}
        self.assertEqual(modulo.extrair_dados_nova_pagina(driver, edital, incluir_homologado=True), {})
        self.assertEqual(driver.navegacoes, [])

    def test_busca_apenas_homologado_sem_clicar_se_link_ja_existe(self):
        driver = DriverFake()
        edital = {'Link': LINK, 'LinkBotao': driver.url_externa}
        driver.texto = 'Valor total homologado: R$ 0,00'
        self.assertEqual(modulo.extrair_dados_nova_pagina(driver, edital, incluir_homologado=True), {'ValorTotalHomologado': 'R$ 0,00'})
        driver.botao.click.assert_not_called()

    def test_detalhe_ausente_registra_timeout_e_restaura_listagem(self):
        driver = DriverFake()
        driver.find_element = Mock(side_effect=NoSuchElementException('Detalhe ausente'))
        erros = []
        self.assertEqual(modulo.extrair_dados_nova_pagina(driver, {'Link': LINK}, lista_erros_api=erros, timeout=0), {})
        self.assertEqual(len(erros), 1)
        self.assertEqual(driver.window_handles, ['listagem'])
        self.assertEqual(driver.current_window_handle, 'listagem')
