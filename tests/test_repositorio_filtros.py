import unittest
from unittest.mock import patch

from pncp_bot_obra.database import repositorio_filtros_obras
from pncp_shared.database import repositoriopncp


class CursorFake:
    def __init__(self, registros):
        self.registros = registros
        self.sql = ""
        self.parametros = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, sql, parametros=None):
        self.sql, self.parametros = sql, parametros

    def fetchall(self):
        return self.registros


class ConexaoFake:
    def __init__(self, cursor):
        self.cursor_fake = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def cursor(self):
        return self.cursor_fake


class RepositorioFiltrosTest(unittest.TestCase):
    def test_shared_consulta_apenas_terms_e_retorna_lista_de_excecoes(self):
        cursor = CursorFake([("suprimento_papelaria*", '["papelaria hospitalar"]')])
        with patch.object(repositoriopncp, "_conectar_banco", return_value=ConexaoFake(cursor)):
            filtros = repositoriopncp.retornar_dicionario_filtros("suprimento_papelaria*")

        self.assertNotIn("term_validation_profiles", cursor.sql)
        self.assertNotIn("id_validation_profile", cursor.sql)
        self.assertEqual(filtros, {"suprimento_papelaria": ["papelaria hospitalar"]})

    def test_obras_consulta_perfil_e_retorna_excecoes_e_valids(self):
        cursor = CursorFake([("agregados*", '["agregado familiar"]', '["BRITA", "PEDRISCO"]')])
        with patch.object(repositorio_filtros_obras, "_conectar_banco", return_value=ConexaoFake(cursor)):
            filtros = repositorio_filtros_obras.retornar_dicionario_filtros_obras("agregados*", manter_word=True)

        self.assertIn("term_validation_profiles", cursor.sql)
        self.assertIn("COALESCE(vp.valid, t.valid)", cursor.sql)
        self.assertEqual(filtros, {"agregados*": {"exceptions": ["agregado familiar"], "valid": ["BRITA", "PEDRISCO"]}})

    def test_shared_retorna_somente_variantes_ativas(self):
        cursor = CursorFake([("Suprimento Papelaria",), ("papelaria",)])
        with patch.object(repositoriopncp, "_conectar_banco", return_value=ConexaoFake(cursor)):
            termos = repositoriopncp.retornar_termos_busca_by_id_page(10009)

        self.assertIn("is_active=1", cursor.sql)
        self.assertEqual(termos, {"suprimento papelaria", "papelaria"})


if __name__ == "__main__":
    unittest.main()
