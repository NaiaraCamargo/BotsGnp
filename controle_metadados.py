import sqlite3

from os.path import isfile
from controle_logs import logs


class ControleMetadados:
    def __init__(self, db_path="metadados.db"):
        self.db_path = db_path
        self._criar_base()

    def _criar_base(self):
        if not isfile(self.db_path):
            logs.info(f"Base {self.db_path} inexistente, criando arquivo...")

        with sqlite3.connect(self.db_path) as conexao:
            conexao.execute("""
                CREATE TABLE IF NOT EXISTS metadados (
                    nome TEXT PRIMARY KEY,
                    valor TEXT
                )
            """)
            conexao.commit()

    def retornar_valor(self, nome="caminho_webdriver"):
        with sqlite3.connect(self.db_path) as conexao:
            cursor = conexao.execute(
                "SELECT valor FROM metadados WHERE nome = ?",
                (nome,)
            )
            retorno = cursor.fetchone()
            return retorno[0] if retorno else None

    def atualizar_valor(self, novo_valor, nome="caminho_webdriver"):
        with sqlite3.connect(self.db_path) as conexao:
            conexao.execute("""
                INSERT INTO metadados (nome, valor)
                VALUES (?, ?)
                ON CONFLICT(nome) DO UPDATE SET valor = excluded.valor
            """, (nome, novo_valor))
            conexao.commit()