import unittest
from urllib.parse import parse_qs, urlparse

from pncp_shared.utils.urls_pncp import definir_pagina_pncp, gerar_urls_variantes_pncp


class UrlsPncpTest(unittest.TestCase):
    def assert_pagina(self, url_original, pagina, parametros_esperados=None):
        parsed = urlparse(definir_pagina_pncp(url_original, pagina))
        query = parse_qs(parsed.query, keep_blank_values=True)
        self.assertEqual(query["pagina"], [str(pagina)])

        for chave, valor in (parametros_esperados or {}).items():
            self.assertEqual(query[chave], [valor])

        return parsed

    def test_atualiza_quando_pagina_e_primeiro_parametro(self):
        self.assert_pagina("https://pncp.gov.br/app/editais?pagina=1&q=obra&status=recebendo_proposta", 2,
                           {"q": "obra", "status": "recebendo_proposta"})

    def test_atualiza_quando_pagina_nao_e_primeiro_parametro(self):
        self.assert_pagina("https://pncp.gov.br/app/editais?q=obra&pagina=1&tam_pagina=20", 3,
                           {"q": "obra", "tam_pagina": "20"})

    def test_adiciona_pagina_quando_parametro_nao_existe(self):
        self.assert_pagina("https://pncp.gov.br/app/editais?q=obra", 4, {"q": "obra"})

    def test_adiciona_pagina_quando_query_nao_existe(self):
        self.assert_pagina("https://pncp.gov.br/app/editais", 5)

    def test_substitui_pagina_atual_diferente_de_um(self):
        self.assert_pagina("https://pncp.gov.br/app/editais?q=obra&pagina=17", 18, {"q": "obra"})

    def test_remove_paginas_duplicadas(self):
        parsed = self.assert_pagina("https://pncp.gov.br/app/editais?pagina=1&q=obra&pagina=9", 2, {"q": "obra"})
        self.assertEqual(len(parse_qs(parsed.query)["pagina"]), 1)

    def test_preserva_termo_codificado_fragmento_e_parametro_vazio(self):
        parsed = self.assert_pagina("https://pncp.gov.br/app/editais?pagina=1&q=constru%C3%A7%C3%A3o&vazio=#resultado", 2,
                                    {"q": "construção", "vazio": ""})
        self.assertEqual(parsed.fragment, "resultado")

    def test_rejeita_pagina_invalida(self):
        for pagina in (0, -1, "invalida"):
            with self.subTest(pagina=pagina), self.assertRaises((TypeError, ValueError)):
                definir_pagina_pncp("https://pncp.gov.br/app/editais?pagina=1", pagina)

    def test_variantes_mantem_original_primeiro_e_ordena_sem_duplicar(self):
        url = "https://pncp.gov.br/app/editais?pagina=7&q=Asfalto&status=recebendo_proposta"
        urls, termo_original = gerar_urls_variantes_pncp(url, {" concreto ", "ASFALTO", "estabilizacao", "Concreto", ""})
        termos = [parse_qs(urlparse(item["url"]).query)["q"][0] for item in urls]

        self.assertEqual(termo_original, "asfalto")
        self.assertEqual(termos, ["asfalto", "concreto", "estabilizacao"])
        self.assertTrue(all(parse_qs(urlparse(item["url"]).query)["pagina"] == ["1"] for item in urls))


if __name__ == "__main__":
    unittest.main()
