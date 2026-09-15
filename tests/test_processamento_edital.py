import unittest
from unittest.mock import patch

from pncp_bot_obra.services import processamento_edital


class ProcessarEditalTest(unittest.TestCase):
    def test_sem_palavra_no_objeto_nem_nos_itens_interrompe_antes_de_salvar(self):
        edital = {"Link": "https://pncp.gov.br/app/editais/12345678901234/2026/1"}
        filtros = {"banco": {"codigo_executor": "EDIT", "palavraschave": {"asfalto*": {"exceptions": [], "valid": ["CONCRETO"]}}}}
        compra = {"objetoCompra": "Aquisicao de materiais administrativos"}

        with patch.object(processamento_edital, "tentar_buscar_compra", return_value=(compra, 0, [], False)), \
             patch.object(processamento_edital, "montar_novos_campos", return_value={}), \
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
        compra = {"objetoCompra": "Aquisicao de materiais administrativos"}

        with patch.object(processamento_edital, "tentar_buscar_compra", return_value=(compra, 0, [], False)), \
             patch.object(processamento_edital, "montar_novos_campos", return_value={"Uf": "RS", "ValorTotalEstimadoCompra": "0"}), \
             patch.object(processamento_edital, "montar_itens_campos", return_value=[]), \
             patch.object(processamento_edital, "obter_pastas_download", return_value=("pasta", "comprimidos")), \
             patch.object(processamento_edital, "buscar_arquivos", return_value=[]) as buscar_arquivos, \
             patch.object(processamento_edital, "gravar_novo_processo", return_value="processo") as gravar_novo_processo, \
             patch.object(processamento_edital, "retornar_destinos_enviados", return_value=set()), \
             patch.object(processamento_edital, "enviar_para_destinos", return_value={"GNP"}):
            resultado = processamento_edital.processar_edital(edital, [], 0, [], filtros, "obra", [], {"GNP"}, [])

        self.assertIs(resultado[0], edital)
        buscar_arquivos.assert_called_once()
        gravar_novo_processo.assert_called_once()

    def test_tratar_timeout_envia_com_token_de_cada_destino_e_aguarda_tres_minutos(self):
        edital = {"Link": "https://pncp.gov.br/app/editais/123/2026/1"}
        destinatarios = [{"id_telegram": "canal-bool", "codigo_destino": "BOOL"},
                         {"id_telegram": "canal-edit", "codigo_destino": "EDIT"}]

        with patch.object(processamento_edital, "enviar_mensagem") as enviar, patch.object(processamento_edital.time, "sleep") as sleep:
            resultado = processamento_edital.tratar_timeout(edital, 0, {"BOOL", "EDIT"}, destinatarios)

        self.assertEqual(resultado, (None, 0))
        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(enviar.call_args_list[0].kwargs, {"erro": True, "destino": "BOOL"})
        self.assertEqual(enviar.call_args_list[0].args[1], ["canal-bool"])
        self.assertEqual(enviar.call_args_list[1].kwargs, {"erro": True, "destino": "EDIT"})
        self.assertEqual(enviar.call_args_list[1].args[1], ["canal-edit"])
        self.assertEqual(enviar.call_args_list[1].args[0]["tentativas_timeout"], 3)
        sleep.assert_called_once_with(180)


if __name__ == "__main__":
    unittest.main()
