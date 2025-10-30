import mysql
import datetime
from ast import literal_eval
from uuid import uuid4
import mysql.connector
from funcoespncp import *
from unidecode import unidecode
from threading import Lock
import mysql.connector.plugins.mysql_native_password

lock_insercao = Lock()

def retornar_dicionario_filtros(word):
    try:
        filtros_aux = {}
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT * FROM terms WHERE is_active = 1 AND word = %s", (word,))
                termos = cursor.fetchall()

                for termo in termos:
                    palavra = termo[1]
                    palavra = palavra.replace("*", "").strip()
                    filtros_aux[palavra] = literal_eval(termo[2])

        return filtros_aux
    except Exception as e:
        logs.error(f"""Nao foi possivel carregar os filtros do Banco: {str(e)}""",exc_info=True )


def retornar_urls(plataforma):
    try:
        retorno_aux = {}
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f'''select pages.id as pagina_id, pages.url, plataformas_page.data_ultima_busca, 
                                    usuarios_crawler_python.id_telegram, plataformas_page.qtd_registros 
                                from plataformas_page 
                                inner join plataformas 
                                inner join plataforma_page_usuarios
                                inner join usuarios_crawler_python
                                inner join pages
                                on plataformas_page.id_pataforma = plataformas.id
                                and pages.id = plataformas_page.id_page
                                and plataformas_page.is_active = 1
                                and plataforma_page_usuarios.id_usuario_crawler_python = usuarios_crawler_python.id 
                                and usuarios_crawler_python.is_active = 1
                                and plataforma_page_usuarios.is_active = 1
                                and plataformas.descricao = '{plataforma}';''')

                for r in cursor.fetchall():
                    # r[1] é a url que esta sendo utilizada como chave
                    if r[1] not in retorno_aux:
                        retorno_aux[r[1]] = {
                            'id_pagina': r[0],
                            'ultima_data': r[2],
                            'ids_usuario': [r[3].strip()],
                            'qtd_registros': r[4]
                        }
                    else:
                        if r[3].strip() not in retorno_aux[r[1]]['ids_usuario']:
                            retorno_aux[r[1]]['ids_usuario'].append(r[3].strip())
        return retorno_aux

    except Exception as e:
        print(f"Erro ao retornar_urls - {str(e)}")
        logs.error(f"Erro ao retornar_urls - {str(e)}", exc_info=True )


def atualizar_ultima_data(id_pagina):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""UPDATE plataformas_page SET data_ultima_busca = '{datetime.now()}' 
                                   WHERE id_page = {id_pagina};""")
                conexao.commit()

    except Exception as e:
        logs.error(f"Erro ao atualizar a ultima data: {str(datetime.now())} - pagina: {str(id_pagina)} - {str(e)}")

def atualizar_banco_pncp(edital, cursor, dados_existentes):
    try:
        editalnovo = {}
        editalnovo.update(edital)
        editalnovo.update(dados_existentes)
        
        
        if 'SituacaoAtual' in editalnovo:
            query_processos = """UPDATE processos SET situacao = %s, updated_at %s WHERE id = %s"""
            valores_processos = (
                validar_campo_banco('SituacaoAtual', editalnovo, 100),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  
                editalnovo['Id']
            )
            cursor.execute(query_processos, valores_processos)

        if 'DataAtual' in editalnovo:
            query_processos = """UPDATE processos SET data = %s, updated_at %s WHERE id = %s"""
            valores_processos = (
                validar_campo_banco('DataAtual', editalnovo, 60),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  
                editalnovo['Id']
            )
            cursor.execute(query_processos, valores_processos)
            
        if 'DataFimAtual' in editalnovo:
            query_pncp = """UPDATE processos_pncp SET data_fim_recebimento_proposta = %s
                         WHERE id_processo = %s"""

            valores_pncp = (
                validar_campo_banco('DataFimAtual', editalnovo, 60),
                editalnovo['Id']  
            )
            cursor.execute(query_pncp, valores_pncp)
            
        if 'QuantidadeAtual' in edital:
            query_pncp = """UPDATE processos_pncp SET quantidade_total_itens = %s
                         WHERE id_processo = %s"""

            valores_pncp = (
                validar_campo_banco('QuantidadeAtual', editalnovo, 100), 
                editalnovo['Id']  
            )
            cursor.execute(query_pncp, valores_pncp)
            
  
    except Exception as e:
        logs.error(f"""Erro ao atualizar Banco - {str(edital)} - {str(e)}""", exc_info=True )


def atualizar_envio_notificacao(novo_id, cursor, editalnovo):
    try:
        cursor.execute(f"""UPDATE processos SET 
                                envio_notificacao = '{datetime.now()}'
                            WHERE id = '{novo_id}'""")
    except Exception as e:
        logs.info(f"""Erro ao atualizar data de envio da notificação - {str(editalnovo)} - {str(e)}""")


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


def retornar_processos(filtros):
    processos = []
    query_parts = []
    parametros = []

    plataforma = filtros.get("plataforma", "").lower()
    data_inicial = filtros.get("data_inicial", "").strip()
    data_final = filtros.get("data_final", "").strip()

    if data_inicial:
        query_parts.append("STR_TO_DATE(SUBSTRING(TRIM(data), 1, 10), '%d/%m/%Y') >= %s")
        parametros.append(data_inicial)

    if data_final:
        query_parts.append("STR_TO_DATE(SUBSTRING(TRIM(data), 1, 10), '%d/%m/%Y') <= %s")
        parametros.append(data_final)

    if plataforma == "pncp":
        query_parts.append("processos.id_page IN (10000, 13213, 13214, 13215)")
    elif plataforma.startswith("obra"):
        query_parts.append("processos.id_page IN (10000, 13213, 13214, 13215, 13216, 13217, 13218)")

    where_extra = ""
    if query_parts:
        where_extra = " AND " + " AND ".join(query_parts)

    query_final = (
        "SELECT * FROM processos "
        "LEFT JOIN processos_pncp ON processos.id = processos_pncp.id_processo "
        "WHERE 1=1" + where_extra +
        " ORDER BY STR_TO_DATE(SUBSTRING(TRIM(data), 1, 10), '%d/%m/%Y') DESC"
    )

    with mysql.connector.connect(
        host=config('host'),
        port=int(config('port')),
        user=config('user'),
        password=config('password'),
        database=config('database')
    ) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            cursor.execute(query_final, parametros)
            processos = cursor.fetchall()

    return processos


def retornar_plataformas(id_plat=''):
    plataformas = {}
    usuarios = {}
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                 password=config("password"), database=config("database")) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            cursor.execute(f"""select plataformas.id as id_plataforma, 
                                     plataformas.descricao as descricao_plataforma,
                                     plataformas_page.id as id_plataforma_page,
                                     plataformas_page.id_page as id_page,
                                     plataformas_page.referencia_codigo as instrucao,
                                     plataformas_page.is_active as pagina_plataforma_ativa,
                                     usuarios_crawler_python.id as usuario_id,
                                     usuarios_crawler_python.nome as usuario_nome,
                                     usuarios_crawler_python.is_active as usuario_ativo,
                                     usuarios_crawler_python.id_telegram as usuario_id_telegram,
                                     usuarios_crawler_python.email as usuario_email,
                                     pages.url as url
                              from plataformas 
                                inner join plataformas_page on plataformas.id = plataformas_page.id_pataforma
                                inner join plataforma_page_usuarios on plataformas_page.id = plataforma_page_usuarios.id_pataforma_pages
                                inner join usuarios_crawler_python on plataforma_page_usuarios.id_usuario_crawler_python = usuarios_crawler_python.id
                                inner join pages on pages.id = plataformas_page.id_page
                                {'' if id_plat == '' else f'AND plataformas.id = {id_plat}'}""")
            for r in cursor.fetchall():
                if r['id_plataforma'] not in plataformas:
                    plataformas[r['id_plataforma']] = {
                        'id_plataforma': r['id_plataforma'],
                        'nome': r['descricao_plataforma'],
                        'urls': {
                            r['url']: {
                                'id_page': r['id_page'],
                                'ativo': 'true' if r['pagina_plataforma_ativa'] == 1 else 'false',
                                'id_plataforma_page': r['id_plataforma_page'],
                                'instrucao': r['instrucao'],
                                'usuarios': [r['usuario_id_telegram']]
                            }
                        }
                    }
                    usuarios['id_telegram'] = {
                        'id': r['usuario_id'],
                        'is_active': 'false' if r['usuario_ativo'] is None or r['usuario_ativo'] == 0 else 'true',
                        'nome': r['usuario_nome'],
                        'id_telegran': r['usuario_id_telegram'],
                        'email': r['usuario_email']
                    }
                else:
                    if r['id_plataforma'] not in plataformas[r['id_plataforma']]['urls']:
                        plataformas[r['id_plataforma']]['urls'][r['url']] = {
                            'id_page': r['id_page'],
                            'ativo': 'true' if r['pagina_plataforma_ativa'] == 1 else 'false',
                            'id_plataforma_page': r['id_plataforma_page'],
                            'instrucao': r['instrucao'],
                            'usuarios': [r['usuario_id_telegram']]
                        }
                    elif r['usuario_id_telegram'] not in plataformas[r['id_plataforma']]['urls'][r['url']]['usuarios']:
                        plataformas[r['id_plataforma']]['urls'][r['url']]['usuarios'].append(r['usuario_id_telegram'])

    return plataformas


def retornar_usuarios(trazer_plataformas=False):
    usuarios = {}
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                 password=config("password"), database=config("database")) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            cursor.execute("""select usuarios_crawler_python.id as id_usuario, 
                                    usuarios_crawler_python.nome as nome_usuario,
                                    usuarios_crawler_python.is_active as usuario_ativo, 
                                    usuarios_crawler_python.id_telegram as id_telegram, 
                                    usuarios_crawler_python.email as email,
                                    plataforma_page_usuarios.is_active as usuario_pagina_ativo,
                                    plataformas_page.id_pataforma as id_plataforma, 
                                    pages.id as pagina_id, 
                                    pages.url as url
                                from usuarios_crawler_python 
                                inner join plataforma_page_usuarios on plataforma_page_usuarios.id_usuario_crawler_python = usuarios_crawler_python.id
                                inner join plataformas_page on plataformas_page.id = plataforma_page_usuarios.id_pataforma_pages
                                inner join pages on plataformas_page.id_page = pages.id;""")

            for r in cursor.fetchall():
                if r["id_usuario"] not in usuarios:
                    usuarios[r["id_usuario"]] = {
                        "nome": r['nome_usuario'],
                        "id_usuario": r["id_usuario"],
                        "id_telegram": r['id_telegram'],
                        "ativo": 'false' if r['usuario_ativo'] is None or r['usuario_ativo'] == 0 else 'true',
                        "urls": {
                            r['url']: {
                                'pagina_ativo': 'false' if r['usuario_pagina_ativo'] is None or r['usuario_pagina_ativo'] == 0 else 'true',
                                'id_url': r['pagina_id'],
                                'id_plataforma': r['id_plataforma']
                            }
                        }
                    }
                else:
                    usuarios[r["id_usuario"]]["urls"][r['url']] = {
                        'pagina_ativo': 'false' if r['usuario_pagina_ativo'] is None or r['usuario_pagina_ativo'] == 0 else 'true',
                        'id_url': r['pagina_id'],
                        'id_plataforma': r['id_plataforma']
                    }
    return usuarios


def retornar_paginas(url=''):
    paginas = []
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                 password=config("password"), database=config("database")) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            cursor.execute(f"""select * from pages {'' if url == '' else f" WHERE pages.url = '{url}'"}""")
            for pagina in cursor.fetchall():
                paginas.append(pagina)

    return paginas


def atualizar_heuristica(id_pagina, qtd_itens):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute(f"""UPDATE plataformas_page SET qtd_registros = '{qtd_itens}' 
                                                   WHERE id_page = {id_pagina};""")
                conexao.commit()

    except Exception as e:
        logs.error(f"Erro ao atualizar a heuristica: {qtd_itens} - pagina: {str(id_pagina)} - {str(e)}")

def verificar_existencia_edital_new(link, orgao, numero):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                resultado = []

                # Buscar por link
                if link != "":
                    cursor.execute(f"""SELECT * FROM processos WHERE link = '{link}';""")
                    resultado = cursor.fetchall()

                # # Se nao encontrar por link busca por Orgao e Numero
                # if len(resultado) == 0 and orgao != "" and numero != "":
                #     cursor.execute(f"""SELECT * FROM processos 
                #                        WHERE orgao = '{orgao}' 
                #                        AND numero = '{numero}';
                #                     """)
                #     resultado = cursor.fetchall()
                    
            return resultado
               
    except Exception as e:
        logs.info(f"""Erro verificar_existencia_edital_new nao foi possivel conectar ao banco - {str(e)}""")
        

    
    
def gravar_novo_processo(editalnovo, plataforma):
    print(f"Gravar novo processo (por link): {editalnovo.get('Link', 'Link não encontrado')}")
   
    try:
        # Conecta ao banco de dados e cria um cursor
        with lock_insercao: 
            with mysql.connector.connect(
                    host=config('host'), port=int(config('port')), user=config('user'),
                    password=config("password"), database=config("database")) as conexao:

                with conexao.cursor(dictionary=True) as cursor:
                    novo_id = None  # Variável para armazenar o id do novo processo

                    # Verifica duplicidade pelo link e insere no banco
                    cursor.execute("SELECT id FROM processos WHERE link = %s", (editalnovo['Link'].rstrip('/'),))
                    if cursor.fetchone():
                        print(f"Edital já existe no banco (por link), ignorando: {editalnovo['Link']}")
                        logs.info(f"Edital já existe no banco (por link), ignorando: {editalnovo['Link']}\n")
                    else:
                        # Gera ID único para o novo processo
                        novo_id = str(uuid4())
                        data_criacao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        envio_notificacao = editalnovo.get('envio_notificacao', None) 
                        num_aux =  editalnovo.get('NumeroAux') or None

                        sql = """INSERT INTO processos (
                                    id, id_page, link, descricao, numero, data,
                                    municipio, uf, licitacao, situacao, orgao,
                                    termos, created_at, updated_at, envio_notificacao, numero_aux
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s
                                )"""

                        valores = (
                            novo_id, editalnovo['id_pagina'], validar_campo_banco('Link', editalnovo, 400),
                            validar_campo_banco('Descricao', editalnovo, 600), validar_campo_banco('Numero', editalnovo, 60),
                            validar_campo_banco('Data', editalnovo, 60), validar_campo_banco('Municipio', editalnovo, 200),
                            validar_campo_banco('Uf', editalnovo, 2), validar_campo_banco('Licitacao', editalnovo, 100),
                            validar_campo_banco('Situacao', editalnovo, 100), validar_campo_banco('Orgao', editalnovo, 200),
                            validar_campo_banco('palavras_chave', editalnovo, 150), data_criacao, envio_notificacao, num_aux
                        )

                        cursor.execute(sql, valores)

                       
                        id_pncp = str(uuid4())
                        editalnovo['Cnpj'] = limpar_cnpj(editalnovo['Cnpj'])  # Garante CNPJ limpo
                        link_aux = editalnovo.get('LinkBotao') or None

                        # Campos base obrigatórios
                        colunas = [
                            "id", "id_processo", "id_contratacao_pncp", "cnpj",
                            "valor_total_estimado_compra", "quantidade_total_itens",
                            "data_inicio_recebimento_proposta", "data_fim_recebimento_proposta",
                            "codigo_unidade_compradora", "link_auxiliar"
                        ]
                        valores = [
                            id_pncp, novo_id,
                            validar_campo_banco('IdContratacaoPncp', editalnovo, 256),
                            validar_campo_banco('Cnpj', editalnovo, 14),
                            validar_campo_banco('ValorTotalEstimadoCompra', editalnovo, 100),
                            validar_campo_banco('QuantidadeItens', editalnovo, 100),
                            validar_campo_banco('DataInicioRecebimentoProposta', editalnovo, 60),
                            validar_campo_banco('DataFimRecebimentoProposta', editalnovo, 60),
                            validar_campo_banco('CodigoUnidadeCompradora', editalnovo, 50),
                            link_aux
                        ]

                        # Adiciona dinamicamente os campos link_reserva_{i}, horario_arq_anexado_{i}, diferenca_inicio_e_anexo_{i}
                        for i in range(1, 5):
                            link_key = f"link_reserva_{i}"
                            horario_key = f"horario_arq_anexado_{i}"
                            diferenca_key = f"diferenca_inicio_e_anexo_{i}"

                            if editalnovo.get(link_key) or editalnovo.get(horario_key) or editalnovo.get(diferenca_key):
                                colunas.extend([link_key, horario_key, diferenca_key])
                                valores.extend([
                                    str(editalnovo.get(link_key, '')),
                                    str(editalnovo.get(horario_key, '')),
                                    str(editalnovo.get(diferenca_key, ''))
                                ])
                        # Monta dinamicamente a SQL
                        campos_sql = ", ".join(colunas)
                        placeholders_sql = ", ".join(["%s"] * len(valores))
                        sql_pncp = f"INSERT INTO processos_pncp ({campos_sql}) VALUES ({placeholders_sql})"

                        # Executa
                        cursor.execute(sql_pncp, valores)

                        conexao.commit()
                        print(f"Edital salvo no banco (por link): {editalnovo.get('Link', 'Link não encontrado')} - {novo_id}\n")
                        logs.info(f"Edital salvo no banco (por link): {editalnovo.get('Link', 'Link não encontrado')} - {novo_id}")
                    
                    # Verifica a necessidade de notificação
                    if editalnovo.get("notificar_retorno") is True:
                        if novo_id:  # Verifica se o novo id foi obtido
                            atualizar_envio_notificacao(novo_id, cursor, editalnovo)  # Passa o id para atualizar

            return True  
    except Exception as e:
        logs.error(f"Erro ao gravar novo processo - {str(editalnovo)} - {str(e)}")
        return False
              
def retornar_registro_paginas(idPagina, idPlataforma):
  try:
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), password=config("password"), database=config("database")) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            query = """
                SELECT qtd_registros 
                FROM plataformas_page 
                WHERE id_page = %s AND id_pataforma = %s
            """
            cursor.execute(query, (idPagina, idPlataforma))
            resultado = cursor.fetchone()  # Retorna um único registro
        
    return resultado["qtd_registros"] if resultado else None

  except Exception as e:
        logs.info(f"""Erro retornar_registro_paginas nao foi possivel conectar ao banco - {str(e)}""")


def retornar_edital_existente_by_plataforma(editalExistente, plataforma):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                resultado = [] 
                
                if plataforma.lower() == 'pncp': 
                    cursor.execute(f"""SELECT * FROM processos_pncp
                                       WHERE id_processo = '{editalExistente['id']}';
                                    """)
                resultado = cursor.fetchall()

            return resultado
               
    except Exception as e:
        logs.info(f"""Erro retornar_edital_existente_by_plataforma nao foi possivel conectar ao banco - {str(e)}""")
            

def gravar_alteracao_processo(alteracoes, dados_existentes, gravar_registro=False):
    try:
        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database")
        ) as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                edital = {"Id": dados_existentes["id"]}

                # Verificar diretamente se "situacao" está em alteracoes e houve mudança
                if "situacao" in alteracoes:
                    antes = alteracoes["situacao"]["antes"]
                    depois = alteracoes["situacao"]["depois"]

                    if antes != depois:
                        edital["status_processo_situacao"] = "Alterado Situacao"
                        edital["SituacaoAnterior"] = antes
                        edital["SituacaoAtual"] = depois
                        logs.info(f"Houve alteração na Situação: {antes} → {depois}")
                        dados_existentes.pop("Situacao", None)
                
                if "data" in alteracoes:
                    antes = alteracoes["data_"]["antes"]
                    depois = alteracoes["data"]["depois"]

                    if antes != depois:
                        edital["status_processo_data"] = "Alterado Data"
                        edital["DataAnterior"] = antes
                        edital["DataAtual"] = depois
                        logs.info(f"Houve alteração na Data: {antes} → {depois}")
                        dados_existentes.pop("data", None) 
                        
                # Verificar diretamente se "data fim recebimento" está em alteracoes e houve mudança
                if "data_fim_recebimento_proposta" in alteracoes:
                    antes = alteracoes["data_fim_recebimento_proposta"]["antes"]
                    depois = alteracoes["data_fim_recebimento_proposta"]["depois"]

                    if antes != depois:
                        edital["status_processo_data_fim"] = "Alterado Data Fim"
                        edital["DataFimAnterior"] = antes
                        edital["DataFimAtual"] = depois
                        logs.info(f"Houve alteração na Data: {antes} → {depois}")
                        dados_existentes.pop("data_fim_recebimento_proposta", None)  # Remove se existir
                        
                if "quantidade_total_itens" in alteracoes:
                    antes = alteracoes["quantidade_total_itens"]["antes"]
                    depois = alteracoes["quantidade_total_itens"]["depois"]
                    
                    if antes != depois:
                        edital["status_processo_itens"] = "Alterado Quantidade de Itens"
                        edital["QuantidadeAnterior"] = antes
                        edital["QuantidadeAtual"] = depois
                        dados_existentes.pop("quantidade_total_itens", None)

               
                # Se houver mudanças, atualizar no banco
                if any(key.startswith("status_processo") for key in edital.keys()):
                    atualizar_banco_pncp(edital, cursor, dados_existentes)
                    conexao.commit() 
                    return edital

    except Exception as e:
        logs.error(f"Erro ao gravar alterações no processo: {e}")
        
        
        
def retorna_processos_banco(ids, data_inicial):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), password=config("password"), database=config("database")) as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                placeholders = ','.join(['%s'] * len(ids))
                query = f"""
                    SELECT * FROM gnpseguros.processos 
                    WHERE id_page IN ({placeholders})
                """
                params = ids

                if data_inicial:
                    query += " AND created_at >= %s"
                    params = ids + [data_inicial]
                    
                cursor.execute(query, params)
                resultados = cursor.fetchall()
                return resultados

    except Exception as e:
        logs.error(f"Erro ao buscar links em banco de dados: {e}")

#carregar_configuracoes()
#verificar_existencia_edital({'notificar_retorno': True, 'Situacao': 'Cancelado', 'Link': 'https://www.portaldecompraspublicas.com.br/processos/ba/prefeitura-municipal-de-casa-nova-2335/de-dle-095-2023-2023-269553'}, 1, [], 'pcp')
