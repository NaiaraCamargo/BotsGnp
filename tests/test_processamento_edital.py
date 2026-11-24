import unittest
from unittest.mock import patch

from pncp_bot_obra.services import processamento_edital


class ProcessarEditalTest(unittest.TestCase):
    def test_sem_palavra_no_objeto_nem_nos_itens_interrompe_antes_de_salvar(self):
        edital = {"Link": "https://pncp.gov.br/app/editais/12345678901234/2026/1"}
        filtros = {"banco": {"codigo_executor": "EDIT", "palavraschave": {"asfalto*": {"exceptions": [], "valid": ["CONCRETO"]}}}}
        edital['Descricao'] = 'Aquisicao de materiais administrativos'

        with patch.object(processamento_edital, "tentar_buscar_itens", return_value=(0, [], False)), \
             patch.object(processamento_edital, "montar_itens_campos", return_value=[]), \
             patch.object(processamento_edital, "buscar_arquivos") as buscar_arquivos, \
             patch.object(processamento_edital, "gravar_novo_processo") as gravar_novo_processo:
            resultado = processamento_edital.processar_edital(edital, [], 0, [], filtros, "obra", [], {"EDIT"}, [])

        self.assertEqual(resultado, (None, 0))
        buscar_arquivos.assert_not_called()
        gravar_novo_processo.assert_not_called()

    def test_gnp_sem_palavra_nao_entra_no_bloqueio_exclusivo_do_edit(self):
        edital = {"Link": "https://pncp.gov.br/app/editais/12345678901234/2026/1"}
        filtros = {"banco": {"codigo_executor": "GNP", "palavraschave": {"asfalto*": {"exceptions": [], "valid": ["CONCRETO"]}}}}
        edital.update(Descricao='Aquisicao de materiais administrativos', Uf='RS', ValorTotalEstimadoCompra='0')

        with patch.object(processamento_edital, "tentar_buscar_itens", return_value=(0, [], False)), \
             patch.object(processamento_edital, "montar_itens_campos", return_value=[]), \
             patch.object(processamento_edital, "obter_pastas_download", return_value=("pasta", "comprimidos")), \
             patch.object(processamento_edital, "buscar_arquivos", return_value=[]) as buscar_arquivos, \
             patch.object(processamento_edital, "complementar_edital"), \
             patch.object(processamento_edital, "gravar_novo_processo", return_value="processo") as gravar_novo_processo, \
             patch.object(processamento_edital, "retornar_destinos_enviados", return_value=set()), \
             patch.object(processamento_edital, "enviar_para_destinos", return_value={"GNP"}):
            resultado = processamento_edital.processar_edital(edital, [], 0, [], filtros, "obra", [], {"GNP"}, [])

        self.assertIs(resultado[0], edital)
        buscar_arquivos.assert_not_called()
        gravar_novo_processo.assert_called_once()

if __name__ == "__main__":
    unittest.main()
