import threading
import unittest
from unittest.mock import patch

from pncp_bot_material_escolar.services import processamento_edital


class ProcessamentoMaterialTest(unittest.TestCase):
    def test_edital_existente_aceita_retorno_em_dicionario(self):
        link = "https://pncp.gov.br/app/editais/88811922000120/2026/102"
        em_processamento = set()

        with patch.object(processamento_edital, "validar_palavras", return_value=[]), \
             patch.object(processamento_edital, "extrair_link", return_value={"Link": link}), \
             patch.object(processamento_edital, "verificar_existencia_edital_new", return_value={"id": 10}), \
             patch.object(processamento_edital, "processar_edital") as processar, \
             patch.object(processamento_edital.logs, "error") as erro:
            resultado = processamento_edital.processar_texto("texto", "material", None, "url", 1, [], 10, False, {},
                                                             threading.Lock(), em_processamento, 0)

        self.assertEqual(resultado, (None, 0))
        self.assertEqual(em_processamento, set())
        processar.assert_not_called()
        erro.assert_not_called()


if __name__ == "__main__":
    unittest.main()
