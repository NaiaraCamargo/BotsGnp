import unittest
from unittest.mock import patch

from pncp_shared.api import compras_pncp


class ComprasPncpTest(unittest.TestCase):
    def test_tentativa_compartilhada_delega_tres_chamadas_ao_cliente(self):
        erros = []

        def falhar(*args, **kwargs):
            erros.append({"tipo_erro": "TIMEOUT_GET_JSON"})
            return None, []

        with patch.object(compras_pncp, "buscar_itens", side_effect=falhar) as buscar:
            resultado = compras_pncp.tentar_buscar_itens("cnpj", "2026", "1", "link", erros)

        self.assertEqual(resultado, (None, [], True))
        buscar.assert_called_once()
        self.assertEqual(buscar.call_args.kwargs["max_tentativas"], 3)

    def test_busca_itens_em_paginas_de_vinte(self):
        compra = {"objetoCompra": "Compra"}
        pagina_um = [{"numeroItem": numero} for numero in range(1, 21)]
        pagina_dois = [{"numeroItem": 21}]

        with patch.object(compras_pncp, "get_json", side_effect=[pagina_um, pagina_dois]) as get_json, \
             patch.object(compras_pncp, "get_int", return_value=21):
            resultado = compras_pncp.buscar_itens("cnpj", "2026", "1", "link", lista_erros_api=[])

        self.assertEqual(len(resultado[1]), 21)
        self.assertEqual(get_json.call_args_list[0].kwargs["params"], {"pagina": 1, "tamanhoPagina": 20})
        self.assertEqual(get_json.call_args_list[1].kwargs["params"], {"pagina": 2, "tamanhoPagina": 20})

    def test_nao_aceita_itens_parciais_quando_uma_pagina_falha(self):
        compra = {"objetoCompra": "Compra"}
        pagina_um = [{"numeroItem": numero} for numero in range(1, 21)]

        with patch.object(compras_pncp, "get_json", side_effect=[pagina_um, None]), \
             patch.object(compras_pncp, "get_int", return_value=21):
            resultado = compras_pncp.buscar_itens("cnpj", "2026", "1", "link", lista_erros_api=[])

        self.assertEqual(resultado, (None, []))

    def test_quantidade_zero_legitima_nao_consulta_paginas(self):
        with patch.object(compras_pncp, 'get_int', return_value=0), patch.object(compras_pncp, 'get_json') as get_json:
            self.assertEqual(compras_pncp.buscar_itens('cnpj', '2026', '1', 'link'), (0, []))
        get_json.assert_not_called()

    def test_falha_de_quantidade_nao_e_confundida_com_zero_sem_lista_externa(self):
        def falhar(*args, **kwargs):
            kwargs['lista_erros_api'].append({'tipo_erro': 'TIMEOUT_GET_JSON'})
            return 0

        with patch.object(compras_pncp, 'get_int', side_effect=falhar):
            self.assertEqual(compras_pncp.tentar_buscar_itens('cnpj', '2026', '1', 'link', None), (None, [], True))

    def test_paginas_incompletas_ou_duplicadas_nao_sao_aceitas(self):
        for itens in ([{'numeroItem': 1}], [{'numeroItem': 1}, {'numeroItem': 1}]):
            with patch.object(compras_pncp, 'get_int', return_value=2), patch.object(compras_pncp, 'get_json', return_value=itens):
                erros = []
                self.assertEqual(compras_pncp.buscar_itens('cnpj', '2026', '1', 'link', lista_erros_api=erros), (None, []))
                self.assertEqual(erros[0]['tipo_erro'], 'ITENS_INCOMPLETOS')

    def test_nao_existe_chamada_http_da_compra(self):
        from unittest.mock import Mock

        respostas = [Mock(json=lambda: 1), Mock(json=lambda: [{'numeroItem': 1}])]
        with patch.object(compras_pncp, 'requisicao_pncp', side_effect=respostas) as requisicao:
            self.assertEqual(compras_pncp.tentar_buscar_itens('cnpj', '2026', '1', 'link', [])[0], 1)
        urls = [chamada.args[1] for chamada in requisicao.call_args_list]
        self.assertEqual([url.rsplit('/1/', 1)[1] for url in urls], ['itens/quantidade', 'itens'])


if __name__ == "__main__":
    unittest.main()
