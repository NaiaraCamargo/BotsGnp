import mysql
from ast import literal_eval
from uuid import uuid4
import mysql.connector
from threading import Lock
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote_plus
import mysql.connector.plugins.mysql_native_password
from pncp_shared.config.controle_config import config
from pncp_shared.utils.funcoespncp import *

lock_insercao = Lock()

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
                                on plataformas_page.id_plataforma = plataformas.id
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

def retornar_dicionario_filtros(word):
    try:
        filtros_aux = {}
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor() as cursor:
                cursor.execute("SELECT * FROM terms WHERE is_active = 1 AND word LIKE %s", (word,))
                termos = cursor.fetchall()

                for termo in termos:
                    palavra = termo[1]
                    palavra = palavra.replace("*", "").strip()
                    filtros_aux[palavra] = literal_eval(termo[2])

        return filtros_aux
    except Exception as e:
        logs.error(f"""Nao foi possivel carregar os filtros do Banco: {str(e)}""",exc_info=True )

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


def retornar_plataformas(id_plat=''):
    plataformas = {}
    usuarios = {}
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                 password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
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
                                    inner join plataformas_page on plataformas.id = plataformas_page.id_plataforma
                                    inner join plataforma_page_usuarios on plataformas_page.id = plataforma_page_usuarios.id_plataforma_pages
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
                                 password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("""select usuarios_crawler_python.id as id_usuario, 
                                        usuarios_crawler_python.nome as nome_usuario,
                                        usuarios_crawler_python.is_active as usuario_ativo, 
                                        usuarios_crawler_python.id_telegram as id_telegram, 
                                        usuarios_crawler_python.email as email,
                                        plataforma_page_usuarios.is_active as usuario_pagina_ativo,
                                        plataformas_page.id_plataforma as id_plataforma, 
                                        pages.id as pagina_id, 
                                        pages.url as url
                                    from usuarios_crawler_python 
                                    inner join plataforma_page_usuarios on plataforma_page_usuarios.id_usuario_crawler_python = usuarios_crawler_python.id
                                    inner join plataformas_page on plataformas_page.id = plataforma_page_usuarios.id_plataforma_pages
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
                                 password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
        with conexao.cursor(dictionary=True) as cursor:
            cursor.execute(f"""select * from pages {'' if url == '' else f" WHERE pages.url = '{url}'"}""")
            for pagina in cursor.fetchall():
                paginas.append(pagina)

    return paginas
       
def atualizar_heuristica(id_pagina: int, qtd_itens: int):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor() as cursor:
                # Atualiza e registra se realmente afetou linha
                cursor.execute("""
                    UPDATE plataformas_page
                    SET qtd_registros = %s
                    WHERE id_page = %s
                """, (int(qtd_itens), int(id_pagina)))

                afetadas = cursor.rowcount
            conexao.commit()

        if afetadas == 0:
            logs.error(f"[heuristica] UPDATE sem efeito (id_page não encontrado?) id_page={id_pagina}, qtd={qtd_itens}")

    except Exception as e:
        logs.error(f"[heuristica] Erro ao atualizar id_page={id_pagina}, qtd={qtd_itens} -> {e}", exc_info=True)

def verificar_existencia_edital_new(link):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor(dictionary=True) as cursor:
                resultado = None

                # Buscar por link
                if link != "":
                    cursor.execute("""
                                    SELECT 
                                        p.id,
                                        p.termos,
                                        pg.filter
                                    FROM processos p
                                    INNER JOIN pages pg ON pg.id = p.id_page
                                    WHERE p.link = %s;
                                """, (link,))
                    resultado = cursor.fetchone()
                   
            return resultado
               
    except Exception as e:
        logs.info(f"""Erro verificar_existencia_edital_new nao foi possivel conectar ao banco - {str(e)}""")
        return None
               
def gravar_processo(cursor, edital):
    try:
        novo_id = None  # Variável para armazenar o id do novo processo
        novo_id = str(uuid4())
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        sql = """
            INSERT INTO processos (
                id, id_page, link, descricao, numero, data,
                municipio, uf, licitacao, situacao, orgao,
                termos, created_at, updated_at, envio_notificacao, numero_aux
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        valores = (
            novo_id, edital['id_pagina'], validar_campo_banco('Link', edital, 400),
            validar_campo_banco('Descricao', edital, 600), validar_campo_banco('Numero', edital, 60),
            validar_campo_banco('Data', edital, 60), validar_campo_banco('Municipio', edital, 200),
            validar_campo_banco('Uf', edital, 2), validar_campo_banco('Licitacao', edital, 100),
            validar_campo_banco('Situacao', edital, 100), validar_campo_banco('Orgao', edital, 200),
            validar_campo_banco('termo_busca', edital, 150),
            now,
            now,
            edital.get("envio_notificacao"),
            edital.get("NumeroAux")
        )

        cursor.execute(sql, valores)
        return novo_id
    except Exception as ex:
        logs.error(f"Erro ao inserir processo - {edital['Link']} \n ERROR: {ex}")
        raise  
    
def gravar_processo_pncp(cursor, edital, id_processo):
    try:
        id_pncp = str(uuid4())
        edital['Cnpj'] = limpar_cnpj(edital['Cnpj'])

        sql = """
            INSERT INTO processos_pncp (
                id, id_processo, id_contratacao_pncp, cnpj,
                valor_total_estimado_compra, quantidade_total_itens,
                data_inicio_recebimento_proposta, data_fim_recebimento_proposta,
                codigo_unidade_compradora, link_auxiliar, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        valores = (
            id_pncp, id_processo,
            validar_campo_banco('IdContratacaoPncp', edital, 256),
            validar_campo_banco('Cnpj', edital, 14),
            validar_campo_banco('ValorTotalEstimadoCompra', edital, 100),
            validar_campo_banco('QuantidadeItens', edital, 100),
            validar_campo_banco('DataInicioRecebimentoProposta', edital, 60),
            validar_campo_banco('DataFimRecebimentoProposta', edital, 60),
            validar_campo_banco('CodigoUnidadeCompradora', edital, 50),
            edital.get("LinkBotao"),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

        cursor.execute(sql, valores)
    
    except Exception as ex:
        logs.error(f"Erro ao inserir processo pncp - {edital['Link']} \n ERROR: {ex}")
        raise  

def gravar_processo_itens(cursor, itens, id_processo):
    sql_item = """
        INSERT INTO processos_itens (
            id, id_processo, numero_item, descricao_item,
            quantidade_item, valor_unit_item, valor_total_item
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s
        )
    """

    for idx, item in enumerate(itens, start=1):
        try:
            valores_item = (
                str(uuid4()),
                id_processo,
                item.get("numeroItem"),
                item.get("descricaoItem"),
                item.get("quantidadeItem"),
                item.get("valorUnitItem"),
                item.get("valorTotalItem"),
            )

            cursor.execute(sql_item, valores_item)

        except Exception as e:
            logs.error(
                "Erro ao inserir item | "
                "indice=%s | numeroItem=%s | descricaoItem=%r | erro=%s",
                idx,
                item.get("numeroItem"),
                item.get("descricaoItem"),
                str(e)
            )
            raise
      
def gravar_novo_processo(editalnovo, plataforma = None):
    link = editalnovo.get("Link", "").rstrip("/")

    print(f"Gravar novo processo (por link): {link or 'Link não encontrado'}")

    if not link:
        logs.error("\nErro ao gravar novo processo: Link não encontrado no edital.")
        return None

    conexao = None

    try:
        conexao = mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin='mysql_native_password'
        )

        with conexao.cursor() as cursor:

            # Verifica duplicidade e retorna o ID já existente
            cursor.execute(
                "SELECT id FROM processos WHERE link = %s LIMIT 1",
                (link,)
            )

            processo_existente = cursor.fetchone()

            if processo_existente:
                id_existente = processo_existente[0]

                print(f"\nEdital já existe no banco (por link), ignorando: {link} - {id_existente}")
                logs.info(f"\nEdital já existe no banco (por link), ignorando: {link} - {id_existente}\n")

                return id_existente

            # Grava novo processo
            id_processo = gravar_processo(cursor, editalnovo)

            if not id_processo:
                logs.error(f"\nNão foi possível obter o id_processo ao gravar: {link}\n")
                conexao.rollback()
                return None

            gravar_processo_pncp(cursor, editalnovo, id_processo)

            if "itens_dados" in editalnovo and editalnovo["itens_dados"] and (plataforma is None or plataforma.lower() != "seguro"):
                gravar_processo_itens(cursor, editalnovo["itens_dados"], id_processo)

            # Atualiza envio de notificação antes do commit
            if editalnovo.get("notificar_retorno") is True:
                atualizar_envio_notificacao(id_processo, cursor, editalnovo)

            conexao.commit()

            print(f"Edital salvo no banco (por link): {link} - {id_processo}\n")
            logs.info(f"\nEdital salvo no banco (por link): {link} - {id_processo}")

            return id_processo

    except Exception as ex:
        logs.error(f"Erro ao gravar novo processo - {link} \n ERROR: {ex}", exc_info=True)

        if conexao:
            try:
                conexao.rollback()
            except Exception:
                pass

        return None

    finally:
        if conexao:
            try:
                conexao.close()
            except Exception:
                pass
              
def retornar_registro_paginas(idPagina, idPlataforma):
  try:
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                 password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
        with conexao.cursor(dictionary=True) as cursor:
            query = """
                SELECT qtd_registros 
                FROM plataformas_page 
                WHERE id_page = %s AND id_plataforma = %s
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
            with conexao.cursor() as cursor:
                resultado = [] 
                
                if plataforma.lower() == 'pncp': 
                    cursor.execute(f"""SELECT * FROM processos_pncp
                                       WHERE id_processo = '{editalExistente['id']}';
                                    """)
                resultado = cursor.fetchall()

            return resultado
               
    except Exception as e:
        logs.info(f"""Erro retornar_edital_existente_by_plataforma nao foi possivel conectar ao banco - {str(e)}""")
        
def salvar_urls_com_erro_api(lista_erros_api, id_pagina=None, plataforma=None):
    if not lista_erros_api:
        return 0

    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                sql = """
                    INSERT INTO urls_erros_api(id_pagina, plataforma, url, params, tipo_erro,
                        mensagem, link_origem, data_erro, status, attempts)
                    VALUES( %s, %s, %s, %s, %s, %s, %s, %s, 'pendente', 0)"""

                dados = []

                for erro in lista_erros_api:
                    dados.append((
                        id_pagina,
                        plataforma,
                        erro.get("url"),
                        erro.get("params"),
                        erro.get("tipo_erro"),
                        erro.get("mensagem"),
                        erro.get("link_origem"),
                        erro.get("data_erro")
                    ))

                cursor.executemany(sql, dados)

            conexao.commit()

        total = len(lista_erros_api)
        lista_erros_api.clear()

        logs.info(f"{total} URLs com erro de API salvas no banco. plataforma={plataforma}, id_pagina={id_pagina}")

        return total

    except Exception as e:
        logs.error(f"Erro ao salvar URLs com erro de API: {e}", exc_info=True)
        return 0
    
def retornar_qtd_registros_heuristica_busca(id_page: int, id_plataforma: int, termo_busca: str) -> int:
    termo_busca = str(termo_busca or "").strip().lower()

    if not termo_busca:
        termo_busca = "sem_termo"

    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT qtd_registros
                    FROM plataformas_page_heuristica_busca
                    WHERE id_page = %s
                      AND id_plataforma = %s
                      AND termo_busca = %s
                    LIMIT 1
                """, (id_page, id_plataforma, termo_busca))

                row = cursor.fetchone()

                if not row:
                    return 0

                return int(row[0] or 0)

    except Exception as e:
        logs.error(f"Erro retornar_qtd_registros_heuristica_busca: {e}", exc_info=True)
        return 0
    
def atualizar_heuristica_busca(id_page: int, id_plataforma: int, termo_busca: str, qtd_registros: int):
    termo_busca = str(termo_busca or "").strip().lower()

    if not termo_busca:
        termo_busca = "sem_termo"

    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), 
                                    user=config('user'), password=config("password"), 
                                    database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO plataformas_page_heuristica_busca
                    (
                        id_page,
                        id_plataforma,
                        termo_busca,
                        qtd_registros,
                        data_ultima_busca,
                        created_at,
                        updated_at
                    )
                    VALUES
                    (
                        %s, %s, %s, %s, NOW(), NOW(), NOW()
                    )
                    ON DUPLICATE KEY UPDATE
                        qtd_registros = VALUES(qtd_registros),
                        data_ultima_busca = NOW(),
                        updated_at = NOW()
                """, (id_page, id_plataforma, termo_busca, int(qtd_registros or 0)))

            conexao.commit()

    except Exception as e:
        logs.error(f"Erro atualizar_heuristica_busca: {e}", exc_info=True)
        
        
def retornar_termos_busca_by_id_page(id_pagina):
    termos_busca= []
    try:
        with mysql.connector.connect(
            host=config('host'), 
            port=int(config('port')), 
            user=config('user'),
            password=config("password"), 
            database=config("database"), 
            auth_plugin='mysql_native_password'
            ) as conexao:
            
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        SELECT termo_busca
                        FROM plataformas_page_heuristica_busca
                        WHERE id_page = %s
                        """, (id_pagina,))
                    
                    resultados = cursor.fetchall()

                    termos_busca = set()

                    for linha in resultados:
                        termo = linha[0]

                        if termo:
                            termos_busca.add(termo.strip().lower())

                    return termos_busca             
            
    except Exception as e:
        logs.error(f"Erro retornar_termos_busca_by_id_page: {e}", exc_info=True)
        
def retornar_emails_planilha_botbool():
    try:
        emails = []

        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin="mysql_native_password"
        ) as conexao:

            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT email
                    FROM email_planilha_botbool
                    WHERE is_active = 1
                """)

                registros = cursor.fetchall()

                for item in registros:
                    email = str(item.get("email", "")).strip()

                    if email:
                        emails.append(email)

        return emails

    except Exception as e:
        logs.error(f"Erro ao buscar e-mails da planilha BotBool: {e}", exc_info=True)
        return []
    
def gravar_processo_botbool_envio(id_processo):
    try:
        if not id_processo:
            return False

        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin="mysql_native_password"
        ) as conexao:

            with conexao.cursor() as cursor:
                cursor.execute("""
                    INSERT IGNORE INTO processos_botbool_envio (
                        id_processo,
                        data_registro,
                        enviado_email
                    )
                    VALUES (
                        %s,
                        NOW(),
                        0
                    )
                """, (str(id_processo),))

                conexao.commit()

        return True

    except Exception as e:
        logs.error(f"Erro ao gravar processo BotBool para envio: {e}", exc_info=True)
        return False

def retornar_processos_botbool_ontem():
    processos = []
    try:
    
        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin="mysql_native_password"
        ) as conexao:

            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT p.*, pn.*, b.data_registro AS data_registro_botbool,
                        b.enviado_email,
                        b.data_envio_email,
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
                    FROM processos_botbool_envio b
                    INNER JOIN processos p ON p.id = b.id_processo
                    LEFT JOIN processos_pncp pn ON pn.id_processo = p.id
                     WHERE b.enviado_email = 0
                      AND b.data_registro >= CURDATE() - INTERVAL 1 DAY
                      AND b.data_registro < CURDATE()
                    ORDER BY p.created_at ASC
                """)

                registros = cursor.fetchall()

                for r in registros:
                    if r.get("itens"):
                        r["itens"] = json.loads(r["itens"])
                    else:
                        r["itens"] = []
                    processos.append(r)

        return processos

    except Exception as e:
        logs.error(f"Erro ao retornar processos BotBool do dia anterior: {e}", exc_info=True)
        return []
    
    
def marcar_processos_botbool_enviados_dia_anterior():
    try:
        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin='mysql_native_password'
        ) as conexao:

            with conexao.cursor() as cursor:
                cursor.execute("""
                    UPDATE processos_botbool_envio
                    SET enviado_email = 1,
                        data_envio_email = NOW()
                    WHERE DATE(data_registro) = CURDATE() - INTERVAL 1 DAY
                      AND enviado_email = 0
                """)

                conexao.commit()

        return True

    except Exception as e:
        logs.error(
            f"Erro ao marcar processos BotBool como enviados: {e}",
            exc_info=True
        )
        return False
    
def atualizar_termos_edital(id_processo, termos):
    try:
        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin='mysql_native_password'
        ) as conexao:

            with conexao.cursor() as cursor:
                cursor.execute("""
                    UPDATE processos
                    SET termos = %s, updated_at = NOW()
                    WHERE id = %s
                """, (validar_campo_banco('termos', {'termos': termos}, 150), id_processo))

                conexao.commit()

        return True

    except Exception as e:
        logs.error(f"Erro ao atualizar termos do edital: {e}", exc_info=True)
        return False
    
#####################################################################################
######## METODOS PARA FUNCIONALIDADE COM QUEUE(FILA) ################################
#####################################################################################


LOCK_SECONDS = 10 * 60   # 20 min

def _extrair_q(url: str) -> str:
    try:
        qs = parse_qs(urlparse(url).query)
        return unquote_plus((qs.get("q", [""])[0] or "")).strip().lower()
    except Exception:
        return ""

def _calcular_prioridade(url: str, id_page: int) -> int:
    return 30

def enfileirar_paginas_plataforma(plataforma: str):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor() as cursor:
                # pega id da plataforma
                cursor.execute("SELECT id FROM plataformas WHERE descricao=%s LIMIT 1", (plataforma,))
                row = cursor.fetchone()
                if not row:
                    return
                id_plataforma = int(row[0])

                # enfileira pages ativas (uma por id_page)
                cursor.execute("""
                    INSERT INTO plataformas_page_queue (id_plataforma, id_page, prioridade, status, next_run_at)
                    SELECT pp.id_plataforma,
                           pp.id_page,
                           100,
                           'queued',
                           NOW()
                    FROM plataformas_page pp
                    WHERE pp.is_active = 1
                      AND pp.id_plataforma = %s
                      AND NOT EXISTS (
                        SELECT 1 FROM plataformas_page_queue q
                        WHERE q.id_plataforma = pp.id_plataforma
                          AND q.id_page = pp.id_page
                          AND q.status IN ('queued','running')
                      )
                """, (id_plataforma,))
            conexao.commit()
    except Exception as e:
        print(f"Erro enfileirar_paginas_plataforma: {e}")
        logs.error(f"Erro enfileirar_paginas_plataforma: {e}", exc_info=True)

def pegar_proximo_job(plataforma: str, worker_id: str):
    try:
        with mysql.connector.connect(
            host=config('host'),
            port=int(config('port')),
            user=config('user'),
            password=config("password"),
            database=config("database"),
            auth_plugin='mysql_native_password'
        ) as conexao:

            with conexao.cursor(dictionary=True) as cursor:

                # 1. Busca a plataforma
                cursor.execute("""
                    SELECT id
                    FROM plataformas
                    WHERE descricao = %s
                    LIMIT 1
                """, (plataforma,))

                p = cursor.fetchone()

                if not p:
                    logs.warning(f"[PEGAR JOB] Plataforma não encontrada: {plataforma}")
                    return None

                id_plataforma = int(p["id"])
                lock_until = datetime.now() + timedelta(seconds=LOCK_SECONDS)

                # 2. Descobre qual job está elegível
                cursor.execute("""
                    SELECT q.id AS job_id
                    FROM plataformas_page_queue q
                    INNER JOIN plataformas_page pp
                        ON pp.id_plataforma = q.id_plataforma
                       AND pp.id_page = q.id_page
                       AND pp.is_active = 1
                    INNER JOIN pages pg
                        ON pg.id = q.id_page
                       AND pg.is_active = 1
                    WHERE q.id_plataforma = %s
                      AND q.status = 'queued'
                      AND q.next_run_at <= NOW()
                      AND (q.lock_until IS NULL OR q.lock_until < NOW())
                    ORDER BY q.prioridade ASC, q.next_run_at ASC, q.id ASC
                    LIMIT 1
                """, (id_plataforma,))

                row = cursor.fetchone()

                if not row:
                    logs.info(f"[PEGAR JOB] Nenhum job elegível para plataforma={plataforma}")
                    return None

                job_id = row["job_id"]

                # 3. Tenta travar exatamente esse job
                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET status = 'running',
                        locked_by = %s,
                        lock_until = %s
                    WHERE id = %s
                      AND id_plataforma = %s
                      AND status = 'queued'
                      AND next_run_at <= NOW()
                      AND (lock_until IS NULL OR lock_until < NOW())
                """, (worker_id, lock_until, job_id, id_plataforma))

                conexao.commit()

                if cursor.rowcount != 1:
                    logs.info(
                        f"[PEGAR JOB] Job {job_id} não foi travado. "
                        f"Provavelmente outro worker pegou antes."
                    )
                    return None

                # 4. Busca os dados completos do job travado
                cursor.execute("""
                    SELECT 
                        q.id AS job_id,
                        q.id_plataforma,
                        q.id_page,
                        q.prioridade,
                        q.attempts,
                        q.max_attempts,

                        pg.url,
                        pg.filter,
                        pg.name,

                        pp.data_ultima_busca AS ultima_data,
                        pp.qtd_registros,

                        GROUP_CONCAT(DISTINCT u.id_telegram SEPARATOR ',') AS ids_usuarios

                    FROM plataformas_page_queue q

                    INNER JOIN plataformas_page pp
                        ON pp.id_plataforma = q.id_plataforma
                       AND pp.id_page = q.id_page
                       AND pp.is_active = 1

                    INNER JOIN pages pg
                        ON pg.id = q.id_page
                       AND pg.is_active = 1

                    LEFT JOIN plataforma_page_usuarios ppu
                        ON ppu.id_plataforma_pages = pp.id_plataforma
                       AND ppu.is_active = 1

                    LEFT JOIN usuarios_crawler_python u
                        ON u.id = ppu.id_usuario_crawler_python
                       AND u.is_active = 1

                    WHERE q.id = %s
                      AND q.status = 'running'
                      AND q.locked_by = %s

                    GROUP BY 
                        q.id,
                        q.id_plataforma,
                        q.id_page,
                        q.prioridade,
                        q.attempts,
                        q.max_attempts,
                        pg.url,
                        pp.data_ultima_busca,
                        pp.qtd_registros

                    LIMIT 1
                """, (job_id, worker_id))

                job = cursor.fetchone()

                # 5. Se marcou running mas não conseguiu buscar, libera o job
                if not job:
                    logs.error(
                        f"[PEGAR JOB] Job {job_id} foi marcado como running, "
                        f"mas o SELECT final não retornou dados. Liberando job."
                    )

                    cursor.execute("""
                        UPDATE plataformas_page_queue
                        SET status = 'queued',
                            locked_by = NULL,
                            lock_until = NULL
                        WHERE id = %s
                    """, (job_id,))

                    conexao.commit()
                    return None

                # 6. Calcula prioridade dinâmica
                prioridade = _calcular_prioridade(job["url"], job["id_page"])

                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET prioridade = %s
                    WHERE id = %s
                """, (prioridade, job_id))

                conexao.commit()

                # 7. Prepara lista de usuários
                ids = []

                if job.get("ids_usuarios"):
                    ids = [
                        s.strip()
                        for s in job["ids_usuarios"].split(",")
                        if s.strip()
                    ]

                job["prioridade"] = prioridade
                job["ids_usuario"] = ids
                
                return job

    except Exception as e:
        logs.error(f"Erro pegar_proximo_job: {e}", exc_info=True)
        return None
    
def finalizar_job_queue(job_id: int):
    """
    Sucesso: volta pra queued rápido e zera attempts (falhas consecutivas).
    """
    try:
        proxima = datetime.now()

        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao: 
            with conexao.cursor() as cursor:
                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET status='queued',
                        next_run_at=%s,
                        locked_by=NULL,
                        lock_until=NULL,
                        last_error=NULL,
                        attempts=0
                    WHERE id=%s AND status='running'
                """, (proxima, job_id))
            conexao.commit()
    except Exception as e:
        logs.error(f"Erro finalizar_job_queue(requeue): {e}", exc_info=True)

def falhar_job_queue(job_id: int, err: str):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor(dictionary=True) as cursor:

                cursor.execute("""
                    SELECT attempts, max_attempts
                    FROM plataformas_page_queue
                    WHERE id=%s
                    LIMIT 1
                """, (job_id,))
                row = cursor.fetchone()
                if not row:
                    return

                attempts = int(row["attempts"] or 0) + 1
                max_attempts = int(row["max_attempts"] or 5)

                status = "queued" if attempts < max_attempts else "failed"

                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET status=%s,
                        next_run_at=NOW(),
                        locked_by=NULL,
                        lock_until=NULL,
                        last_error=%s,
                        attempts=%s,
                        updated_at=NOW()
                    WHERE id=%s
                """, (status, (err or "")[:4000], attempts, job_id))

            conexao.commit()

    except Exception as e:
        logs.error(f"Erro falhar_job_queue: {e}", exc_info=True)
        
def requeue_jobs_orfaos(plataforma: str, motivo: str = "Requeue geral"):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT id FROM plataformas WHERE descricao=%s LIMIT 1", (plataforma,))
                row = cursor.fetchone()
                if not row:
                    return 0
                id_plataforma = int(row[0])

                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET status='queued',
                        next_run_at=NOW(),
                        attempts=0,
                        locked_by=NULL,
                        lock_until=NULL,
                        last_error=%s,
                        updated_at=NOW()
                    WHERE id_plataforma=%s
                      AND status IN ('running', 'failed')
                """, (motivo[:4000], id_plataforma))
                afetadas = cursor.rowcount
            conexao.commit()
            return afetadas
    except Exception as e:
        logs.error(f"Erro requeue_jobs_orfaos: {e}", exc_info=True)
        return 0
        
def renovar_lock_job(job_id: int, worker_id: str):
    try:
        lock_until = datetime.now() + timedelta(seconds=LOCK_SECONDS)
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET lock_until=%s,
                        updated_at=NOW()
                    WHERE id=%s
                      AND status IN ('running', 'failed')
                      AND locked_by=%s
                """, (lock_until, job_id, worker_id))
            conexao.commit()
    except Exception as e:
        logs.error(f"Erro renovar_lock_job: {e}", exc_info=True)
        
def requeue_sem_heartbeat(plataforma: str, minutos_sem_heartbeat: int = 10, motivo: str = "Requeue sem heartbeat"):
    try:
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'), 
                                     password=config("password"), database=config("database"), auth_plugin='mysql_native_password') as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT id FROM plataformas WHERE descricao=%s LIMIT 1", (plataforma,))
                row = cursor.fetchone()
                if not row:
                    return 0
                id_plataforma = int(row[0])

                cursor.execute("""
                    UPDATE plataformas_page_queue
                    SET status='queued',
                        next_run_at=NOW(),
                        attempts=0,
                        locked_by=NULL,
                        lock_until=NULL,
                        last_error=%s,
                        updated_at=NOW()
                    WHERE id_plataforma=%s
                      AND status IN ('running', 'failed')
                      AND updated_at < (NOW() - INTERVAL %s MINUTE)
                """, (motivo[:4000], id_plataforma, int(minutos_sem_heartbeat)))

                afetadas = cursor.rowcount
            conexao.commit()
            return afetadas
    except Exception as e:
        logs.error(f"Erro requeue_sem_heartbeat: {e}", exc_info=True)
        return 0
