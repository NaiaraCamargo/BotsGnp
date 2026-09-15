import unittest
from unittest.mock import patch

from pncp_shared.database.repositoriopncp import bloquear_processamento_edital, falhar_job_queue, finalizar_job_queue, gravar_processo_pncp, pegar_proximo_job
from pncp_shared.database.repositoriopncp import retornar_plataformas, retornar_urls
from pncp_shared.database.repositoriopncp import requeue_jobs_orfaos


class CursorFake:
    def execute(self, sql, valores):
        self.sql = sql
        self.valores = valores


class CursorConsultaFake:
    def __init__(self, registros=None, respostas=None):
        self.registros = registros or []
        self.respostas = iter(respostas or [])
        self.execucoes = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, sql, valores=None):
        self.execucoes.append((sql, valores))

    def fetchall(self):
        return self.registros

    def fetchone(self):
        return next(self.respostas)


class ConexaoFake:
    def __init__(self, cursor):
        self.cursor_fake = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def cursor(self, dictionary=False):
        return self.cursor_fake

    def commit(self):
        pass

    def close(self):
        self.closed = True


class GravarProcessoPncpTest(unittest.TestCase):
    def setUp(self):
        self.edital = {"Link": "teste", "Cnpj": "12.345.678/0001-90", "IdContratacaoPncp": "PNCP-1", "ValorTotalEstimadoCompra": "100,00",
                       "ValorTotalHomologado": "90,00", "QuantidadeItens": 1, "DataInicioRecebimentoProposta": "01/01/2026",
                       "DataFimRecebimentoProposta": "02/01/2026", "CodigoUnidadeCompradora": "1", "LinkBotao": "https://exemplo.com"}

    def test_obras_nao_insere_valor_homologado(self):
        cursor = CursorFake()
        gravar_processo_pncp(cursor, self.edital.copy(), "processo-1", "obra")
        self.assertNotIn("valor_total_homologado", cursor.sql)
        self.assertEqual(cursor.sql.count("%s"), len(cursor.valores))

    def test_seguro_insere_valor_homologado(self):
        cursor = CursorFake()
        gravar_processo_pncp(cursor, self.edital.copy(), "processo-1", "seguro")
        self.assertIn("valor_total_homologado", cursor.sql)
        self.assertIn("90,00", cursor.valores)
        self.assertEqual(cursor.sql.count("%s"), len(cursor.valores))


class ConsultasRepositorioPncpTest(unittest.TestCase):
    def test_job_concluido_volta_para_o_fim_da_fila_imediatamente(self):
        cursor = CursorConsultaFake()
        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=ConexaoFake(cursor)):
            finalizar_job_queue(10)

        sql, valores = cursor.execucoes[0]
        self.assertIn("next_run_at=NOW()", sql)
        self.assertEqual(valores, (10,))

    def test_job_com_falha_volta_para_fila_e_preserva_diagnostico(self):
        cursor = CursorConsultaFake(respostas=[{"attempts": 2}])
        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=ConexaoFake(cursor)):
            falhar_job_queue(10, "erro de teste")

        sql, valores = cursor.execucoes[1]
        self.assertIn("status='queued'", sql)
        self.assertNotIn("status=%s", sql)
        self.assertEqual(valores, ("erro de teste", 3, 10))

    def test_requeue_recupera_jobs_failed_e_running_com_lock_expirado(self):
        cursor = CursorConsultaFake(respostas=[(4,)])
        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=ConexaoFake(cursor)):
            requeue_jobs_orfaos("obra", codigo_executor="EDIT")

        sql, valores = cursor.execucoes[1]
        self.assertIn("q.status='failed'", sql)
        self.assertIn("q.status='running'", sql)
        self.assertIn("CASE WHEN q.status='failed' THEN q.last_error", sql)
        self.assertEqual(valores, ("Requeue de lock expirado", 4, "EDIT"))

    def test_lock_do_edital_e_adquirido_e_liberado(self):
        cursor = CursorConsultaFake(respostas=[(1,), (1,)])
        conexao = ConexaoFake(cursor)

        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=conexao):
            with bloquear_processamento_edital("https://edital") as adquirido:
                self.assertTrue(adquirido)

        self.assertIn("GET_LOCK", cursor.execucoes[0][0])
        self.assertIn("RELEASE_LOCK", cursor.execucoes[1][0])
        self.assertTrue(conexao.closed)

    def test_retornar_urls_relaciona_usuario_com_a_pagina_correta(self):
        cursor = CursorConsultaFake(registros=[(1, "url", None, "100", 20), (1, "url", None, "200", 20)])
        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=ConexaoFake(cursor)):
            resultado = retornar_urls("seguro")

        sql, parametros = cursor.execucoes[0]
        self.assertIn("id_plataforma_pages=plataformas_page.id", sql)
        self.assertEqual(parametros, ("seguro",))
        self.assertEqual(resultado["url"]["ids_usuario"], ["100", "200"])

    def test_retornar_plataformas_acumula_usuarios_da_mesma_url(self):
        base = {"id_plataforma": 4, "descricao_plataforma": "obra", "id_plataforma_page": 10, "id_page": 1,
                "instrucao": "", "pagina_plataforma_ativa": 1, "usuario_ativo": 1, "usuario_email": "", "url": "url"}
        registros = [{**base, "usuario_id": 1, "usuario_nome": "A", "usuario_id_telegram": "100"},
                     {**base, "usuario_id": 2, "usuario_nome": "B", "usuario_id_telegram": "200"}]
        cursor = CursorConsultaFake(registros=registros)
        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=ConexaoFake(cursor)):
            resultado = retornar_plataformas()

        self.assertEqual(resultado[4]["urls"]["url"]["usuarios"], ["100", "200"])

    def test_pegar_job_usa_id_da_plataforma_page_para_relacionar_usuario(self):
        job = {"job_id": 10, "id_plataforma": 4, "id_page": 1, "prioridade": 100, "attempts": 0, "max_attempts": 5,
               "url": "url", "filter": "ALL", "name": "obra", "codigo_executor": None, "destinos": None,
               "ultima_data": None, "qtd_registros": 20, "ids_usuarios": "100"}
        cursor = CursorConsultaFake(respostas=[{"id": 4}, {"job_id": 10}, job])
        with patch("pncp_shared.database.repositoriopncp._conectar_banco", return_value=ConexaoFake(cursor)):
            resultado = pegar_proximo_job("obra", "worker")

        sql_dados = next(sql for sql, _ in cursor.execucoes if "LEFT JOIN plataforma_page_usuarios" in sql)
        self.assertIn("ppu.id_plataforma_pages=pp.id", sql_dados)
        self.assertEqual(resultado["ids_usuario"], ["100"])


if __name__ == "__main__":
    unittest.main()
