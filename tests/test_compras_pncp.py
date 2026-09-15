import unittest
from unittest.mock import patch

from pncp_shared.api import compras_pncp


class ComprasPncpTest(unittest.TestCase):
    def test_tentativa_compartilhada_delega_tres_chamadas_ao_cliente(self):
        erros = []

        def falhar(*args, **kwargs):
            erros.append({"tipo_erro": "TIMEOUT_GET_JSON"})
            return None, 0, []

        with patch.object(compras_pncp, "buscar_compra_e_itens", side_effect=falhar) as buscar:
            resultado = compras_pncp.tentar_buscar_compra("cnpj", "2026", "1", "link", erros)

        self.assertEqual(resultado, (None, None, None, True))
        buscar.assert_called_once()
        self.assertEqual(buscar.call_args.kwargs["max_tentativas"], 3)

    def test_busca_itens_em_paginas_de_vinte(self):
        compra = {"objetoCompra": "Compra"}
        pagina_um = [{"numeroItem": numero} for numero in range(1, 21)]
        pagina_dois = [{"numeroItem": 21}]

        with patch.object(compras_pncp, "get_json", side_effect=[compra, pagina_um, pagina_dois]) as get_json, \
             patch.object(compras_pncp, "get_int", return_value=21):
            resultado = compras_pncp.buscar_compra_e_itens("cnpj", "2026", "1", "link", lista_erros_api=[])

        self.assertEqual(len(resultado[2]), 21)
        self.assertEqual(get_json.call_args_list[1].kwargs["params"], {"pagina": 1, "tamanhoPagina": 20})
        self.assertEqual(get_json.call_args_list[2].kwargs["params"], {"pagina": 2, "tamanhoPagina": 20})

    def test_nao_aceita_itens_parciais_quando_uma_pagina_falha(self):
        compra = {"objetoCompra": "Compra"}
        pagina_um = [{"numeroItem": numero} for numero in range(1, 21)]

        with patch.object(compras_pncp, "get_json", side_effect=[compra, pagina_um, None]), \
             patch.object(compras_pncp, "get_int", return_value=21):
            resultado = compras_pncp.buscar_compra_e_itens("cnpj", "2026", "1", "link", lista_erros_api=[])

        self.assertEqual(resultado, (None, 0, []))


if __name__ == "__main__":
    unittest.main()
