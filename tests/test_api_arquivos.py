import unittest
from unittest.mock import patch

from pncp_shared.api import api_arquivos


class ApiArquivosTest(unittest.TestCase):
    def test_lista_arquivos_em_paginas_de_vinte(self):
        pagina_um = [{"sequencialDocumento": numero, "titulo": f"Arquivo {numero}"} for numero in range(1, 21)]
        pagina_dois = [{"sequencialDocumento": 21, "titulo": "Arquivo 21"}]

        with patch.object(api_arquivos, "get_json", side_effect=[pagina_um, pagina_dois]) as get_json:
            arquivos = api_arquivos.buscar_arquivos("cnpj", 2026, 1, "link")

        self.assertEqual(len(arquivos), 21)
        self.assertEqual(get_json.call_args_list[0].kwargs["params"], {"pagina": 1, "tamanhoPagina": 20})
        self.assertEqual(get_json.call_args_list[1].kwargs["params"], {"pagina": 2, "tamanhoPagina": 20})

    def test_descarta_resultado_parcial_se_uma_pagina_falhar(self):
        pagina_um = [{"sequencialDocumento": numero, "titulo": f"Arquivo {numero}"} for numero in range(1, 21)]

        with patch.object(api_arquivos, "get_json", side_effect=[pagina_um, None]):
            arquivos = api_arquivos.buscar_arquivos("cnpj", 2026, 1, "link")

        self.assertEqual(arquivos, [])


if __name__ == "__main__":
    unittest.main()
