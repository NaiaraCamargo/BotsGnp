import unittest
from unittest.mock import Mock, patch

from pncp_shared.controllers.controle_envio_TG import enviar_mensagem


class EnvioTelegramTest(unittest.TestCase):
    @patch("pncp_shared.controllers.controle_envio_TG.sleep")
    @patch("pncp_shared.controllers.controle_envio_TG.requests.post")
    def test_envia_todos_os_destinatarios_recebidos_sem_filtrar_canais_fixos(self, post, _sleep):
        post.return_value = Mock(status_code=200)

        with patch.dict("pncp_shared.controllers.controle_envio_TG.configuracoes", {"token_telegram": "token"}, clear=False):
            enviados = enviar_mensagem("teste", ["-1002657878005", "-1004295198662"])

        self.assertEqual(enviados, ["-1002657878005", "-1004295198662"])
        self.assertEqual(post.call_count, 2)

    @patch("pncp_shared.controllers.controle_envio_TG.sleep")
    @patch("pncp_shared.controllers.controle_envio_TG.requests.post")
    def test_tenta_novamente_quando_telegram_retorna_erro(self, post, _sleep):
        post.side_effect = [Mock(status_code=500, text="erro"), Mock(status_code=200)]

        with patch.dict("pncp_shared.controllers.controle_envio_TG.configuracoes", {"token_telegram": "token"}, clear=False):
            enviados = enviar_mensagem("teste", ["canal"])

        self.assertEqual(enviados, ["canal"])
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
