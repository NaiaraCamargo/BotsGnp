import unittest
from unittest.mock import patch

from pncp_bot_seguro.controllers import controle_botpncp


class ControleSeguroTest(unittest.TestCase):
    def test_processa_todas_as_urls_sequencialmente(self):
        urls = {"url-1": {"id_pagina": 1, "ids_usuario": []}, "url-2": {"id_pagina": 2, "ids_usuario": []}}

        with patch.object(controle_botpncp, "limpar_console"), patch.object(controle_botpncp, "carregar_configuracoes"), \
             patch.object(controle_botpncp, "controle_logs"), patch.object(controle_botpncp, "iniciar_backup_banco_periodico"), \
             patch.object(controle_botpncp, "retornar_urls", return_value=urls), patch.object(controle_botpncp, "executar_url") as executar:
            controle_botpncp.bot("seguro", rodar_infinito=False)

        self.assertEqual([chamada.args[0] for chamada in executar.call_args_list], ["url-1", "url-2"])


if __name__ == "__main__":
    unittest.main()
