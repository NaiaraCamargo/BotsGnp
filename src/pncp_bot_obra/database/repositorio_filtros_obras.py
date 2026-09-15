import json
from ast import literal_eval

import mysql.connector
import mysql.connector.plugins.mysql_native_password

from pncp_shared.config.controle_config import config
from pncp_shared.logs.controle_logs import logs


def _conectar_banco():
    return mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                   password=config("password"), database=config("database"), auth_plugin='mysql_native_password')


def _carregar_lista(valor):
    if valor in (None, ""):
        return []
    if isinstance(valor, list):
        return valor

    try:
        carregado = json.loads(valor)
    except (TypeError, ValueError):
        try:
            carregado = literal_eval(str(valor))
        except (TypeError, ValueError, SyntaxError):
            return []

    return carregado if isinstance(carregado, list) else []


def retornar_dicionario_filtros_obras(word, manter_word=False):
    try:
        filtros = {}
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""SELECT t.word, t.exceptions, COALESCE(vp.valid, t.valid) AS valid FROM terms t
                    LEFT JOIN term_validation_profiles vp ON vp.id=t.id_validation_profile AND vp.is_active=1
                    WHERE t.is_active=1 AND LOWER(TRIM(t.word))=LOWER(TRIM(%s))""", (word,))

                for termo in cursor.fetchall():
                    palavra = termo[0].strip() if manter_word else termo[0].replace("*", "").strip()
                    filtros[palavra] = {"exceptions": _carregar_lista(termo[1]), "valid": _carregar_lista(termo[2])}

        return filtros
    except Exception as e:
        logs.error(f"Nao foi possivel carregar os filtros de Obras: {e}", exc_info=True)
        return {}
