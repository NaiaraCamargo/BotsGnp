import unittest

from pncp_bot_obra.services.roteamento_bots import (
    calcular_destinos_aprovados,
    destinatarios_por_destino,
    normalizar_destinos,
)


class RoteamentoBotsTest(unittest.TestCase):
    def test_normaliza_destinos_validos(self):
        self.assertEqual(normalizar_destinos("gnp, BOOL,desconhecido"), {"GNP", "BOOL"})

    def test_aplica_regras_independentes(self):
        edital = {
            "Uf": "RS",
            "ValorTotalEstimadoCompra": "R$ 700.000,00",
        }

        self.assertEqual(
            calcular_destinos_aprovados(edital, {"GNP", "BOOL", "EDIT"}, True),
            {"GNP", "BOOL", "EDIT"},
        )

    def test_bool_respeita_destino_e_valor(self):
        edital_baixo = {
            "Uf": "SP",
            "ValorTotalEstimadoCompra": "R$ 499.999,99",
        }
        edital_sigiloso = {
            "Uf": "SP",
            "ValorTotalEstimadoCompra": "SIGILOSO",
        }

        self.assertEqual(calcular_destinos_aprovados(edital_baixo, {"BOOL"}), set())
        self.assertEqual(calcular_destinos_aprovados(edital_sigiloso, {"BOOL"}), {"BOOL"})
        self.assertEqual(calcular_destinos_aprovados(edital_sigiloso, {"EDIT"}, True), {"EDIT"})

    def test_destinatario_precisa_ter_destino_configurado(self):
        destinatarios = [
            {"id_telegram": "gnp", "codigo_destino": "GNP"},
            {"id_telegram": "bool", "codigo_destino": "BOOL"},
            {"id_telegram": "edit", "codigo_destino": "EDIT"},
            {"id_telegram": "sem-destino", "codigo_destino": None},
        ]

        self.assertEqual(destinatarios_por_destino(destinatarios, "EDIT"), ["edit"])
        self.assertEqual(destinatarios_por_destino(destinatarios, "BOOL"), ["bool"])


if __name__ == "__main__":
    unittest.main()
