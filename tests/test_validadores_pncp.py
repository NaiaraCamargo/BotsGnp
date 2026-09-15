import unittest

from pncp_shared.utils.validadores_pncp import validar_palavras, validar_perfil_valid, validar_texto_seguro


class ValidadoresPncpTest(unittest.TestCase):
    def test_valid_compartilhado_encontra_no_objeto(self):
        filtros = {
            "banco": {
                "palavraschave": {
                    "asfalto*": {
                        "exceptions": [],
                        "valid": ["CONCRETO USINADO", "CCR"],
                    }
                }
            }
        }

        self.assertTrue(
            validar_perfil_valid(
                texto="Contratacao de concreto-usinado para obra",
                filtros_base=filtros,
            )
        )
        self.assertEqual(validar_palavras(texto="Objeto: Contratacao de concreto-usinado para obra", filtros_base=filtros),
                         ["CONCRETO USINADO"])

    def test_valid_compartilhado_encontra_nos_itens(self):
        filtros = {
            "banco": {
                "palavraschave": {
                    "drenagem*": {
                        "exceptions": [],
                        "valid": ["POCO DE VISITA"],
                    }
                }
            }
        }
        itens = [{"descricaoItem": "Poco de visita pre-moldado"}]

        self.assertTrue(validar_perfil_valid(itens=itens, filtros_base=filtros))
        self.assertEqual(validar_palavras(itens=itens, filtros_base=filtros), ["POCO DE VISITA"])

    def test_validar_palavras_exige_valid_quando_perfil_possui_lista(self):
        filtros = {"banco": {"palavraschave": {"asfalto*": {"exceptions": [], "valid": ["CONCRETO USINADO"]}}}}

        self.assertEqual(validar_palavras(texto="Objeto: aquisicao de asfalto", filtros_base=filtros), [])

    def test_sem_valid_nao_aprova_edit(self):
        filtros = {
            "banco": {
                "palavraschave": {
                    "obra*": {"exceptions": [], "valid": []},
                }
            }
        }

        self.assertFalse(validar_perfil_valid(texto="Obra de concreto", filtros_base=filtros))

    def test_validar_palavras_mantem_compatibilidade_com_lista_antiga(self):
        filtros = {
            "banco": {
                "palavraschave": {
                    "obra*": ["obra de arte"],
                }
            }
        }

        self.assertEqual(
            validar_palavras(texto="Objeto: execucao de obra publica", filtros_base=filtros),
            ["obra"],
        )
        self.assertEqual(
            validar_palavras(texto="Objeto: obra de arte especial", filtros_base=filtros),
            [],
        )

    def test_seguro_mantem_lista_de_excecoes_do_terms(self):
        filtros = {"banco": {"palavraschave": {"segur": ["seguro desemprego"]}}}

        self.assertEqual(validar_texto_seguro("Objeto: seguro residencial", filtros), ["seguro"])
        self.assertEqual(validar_texto_seguro("Objeto: seguro desemprego", filtros), [])


if __name__ == "__main__":
    unittest.main()
