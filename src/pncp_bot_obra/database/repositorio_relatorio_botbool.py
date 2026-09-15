import json

import mysql.connector
import mysql.connector.plugins.mysql_native_password

from pncp_shared.config.controle_config import config
from pncp_shared.logs.controle_logs import logs


def _conectar_banco():
    return mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                   password=config("password"), database=config("database"), auth_plugin='mysql_native_password')


def retornar_emails_planilha_botbool():
    try:
        emails = []

        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT email FROM email_planilha_botbool WHERE is_active=1")

                for item in cursor.fetchall():
                    email = str(item.get("email", "")).strip()
                    if email:
                        emails.append(email)

        return emails
    except Exception as e:
        logs.error(f"Erro ao buscar e-mails da planilha BotBool: {e}", exc_info=True)
        return []

def retornar_processos_botbool_periodo(data_inicial, data_final):
    try:
        processos = []

        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("""SELECT p.*, pn.*, b.data_registro AS data_registro_botbool, b.enviado_email, b.data_envio_email,
                    (SELECT JSON_ARRAYAGG(JSON_OBJECT('numero_item', i.numero_item, 'descricao_item', i.descricao_item,
                        'quantidade_item', i.quantidade_item, 'valor_unit_item', i.valor_unit_item,
                        'valor_total_item', i.valor_total_item)) FROM processos_itens i WHERE i.id_processo=p.id) AS itens
                    FROM processos_botbool_envio b INNER JOIN processos p ON p.id=b.id_processo
                    LEFT JOIN processos_pncp pn ON pn.id_processo=p.id
                    WHERE b.enviado_email=0 AND b.data_registro>=%s AND b.data_registro<%s ORDER BY p.created_at ASC""",
                               (data_inicial, data_final))

                for registro in cursor.fetchall():
                    registro["itens"] = json.loads(registro["itens"]) if registro.get("itens") else []
                    processos.append(registro)

        return processos
    except Exception as e:
        logs.error(f"Erro ao retornar processos BotBool do período: {e}", exc_info=True)
        return []
