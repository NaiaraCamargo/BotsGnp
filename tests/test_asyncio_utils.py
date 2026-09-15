import asyncio
import unittest
from unittest.mock import patch

from pncp_shared.utils.asyncio_utils import executar_com_timeout_suave


class AsyncioUtilsTest(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_suave_aguarda_a_mesma_tarefa_terminar(self):
        eventos = []

        async def operacao():
            eventos.append("inicio")
            await asyncio.sleep(0.02)
            eventos.append("fim")
            return 42

        with patch("pncp_shared.utils.asyncio_utils.logs.warning") as warning:
            resultado = await executar_com_timeout_suave(operacao(), 0.001, "job=1")

        self.assertEqual(resultado, 42)
        self.assertEqual(eventos, ["inicio", "fim"])
        warning.assert_called_once()

    async def test_execucao_rapida_nao_emite_aviso(self):
        async def operacao():
            return "ok"

        with patch("pncp_shared.utils.asyncio_utils.logs.warning") as warning:
            resultado = await executar_com_timeout_suave(operacao(), 1, "job=2")

        self.assertEqual(resultado, "ok")
        warning.assert_not_called()

    async def test_timeout_interno_da_tarefa_continua_sendo_erro(self):
        async def operacao():
            raise asyncio.TimeoutError("timeout interno")

        with patch("pncp_shared.utils.asyncio_utils.logs.warning") as warning:
            with self.assertRaises(asyncio.TimeoutError):
                await executar_com_timeout_suave(operacao(), 1, "job=3")

        warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
