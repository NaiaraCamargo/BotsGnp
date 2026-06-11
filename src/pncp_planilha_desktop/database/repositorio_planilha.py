import mysql
import mysql.connector
import json
import mysql.connector.plugins.mysql_native_password
from pncp_shared.config.controle_config import config
from pncp_shared.utils.funcoespncp import *

def retornar_processos(filtros):
    try:
        processos = []
        query_parts = []
        parametros = []

        link = filtros.get("link_edital", "")
        data_inicial = filtros.get("data_inicial", "").strip()
        data_final = filtros.get("data_final", "").strip()

        if data_inicial:
            query_parts.append("STR_TO_DATE(SUBSTRING(TRIM(p.data), 1, 10), '%d/%m/%Y') >= %s")
            parametros.append(data_inicial)
        if data_final:
            query_parts.append("STR_TO_DATE(SUBSTRING(TRIM(p.data), 1, 10), '%d/%m/%Y') <= %s")
            parametros.append(data_final)
        if link:
            query_parts.append("p.link = %s")
            parametros.append(link)

        where_extra = ""
        if query_parts:
            where_extra = " AND " + " AND ".join(query_parts)

        query_final = f"""
            SELECT
                p.*,
                pn.*,
                (
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'numero_item', i.numero_item,
                            'descricao_item', i.descricao_item,
                            'quantidade_item', i.quantidade_item,
                            'valor_unit_item', i.valor_unit_item,
                            'valor_total_item', i.valor_total_item
                        )
                    )
                    FROM processos_itens i
                    WHERE i.id_processo = p.id
                ) AS itens
            FROM processos p
            LEFT JOIN processos_pncp pn ON pn.id_processo = p.id
            WHERE 1=1
            {where_extra}
            ORDER BY STR_TO_DATE(SUBSTRING(TRIM(p.data), 1, 10), '%d/%m/%Y') DESC
        """

        
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                    password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
                with conexao.cursor(dictionary=True) as cursor:
                    cursor.execute(query_final, parametros)
                    registros = cursor.fetchall()

                    # Converter JSON dos itens
                    for r in registros:
                        if r.get("itens"):
                            r["itens"] = json.loads(r["itens"])
                        else:
                            r["itens"] = []
                        processos.append(r)

        return processos
    except Exception as e:
        logs.error(f"Erro ao retornar processos: {e}", exc_info=True)
        return []



def retornar_periodo_processos(data_inicial=True, data_final=True):
    # Retorna a menor e a maior data armazenada no banco
    d_i = d_f = ""

    try:
        if not data_inicial and not data_final:
            return d_i, d_f

        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor() as cursor:
                if data_inicial:
                    cursor.execute("select min(STR_TO_DATE(substring(TRIM(data), 1, 10), '%d/%m/%Y')) from processos;")
                    data = cursor.fetchone()
                    if data is not None:
                        d_i = str(data[-1])

                if data_final:
                    cursor.execute("select max(STR_TO_DATE(substring(TRIM(data), 1, 10), '%d/%m/%Y')) from processos;")
                    data = cursor.fetchone()
                    if data is not None:
                        d_f = str(data[-1])

        return d_i, d_f
    except Exception as edt:
        logs.info(f"Nao foi possivel encontrar um peridodo de tempo, retornando valor padrao - {str(edt)}")
        return d_i, d_f
