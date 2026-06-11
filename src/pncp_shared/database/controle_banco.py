import webview
import mysql.connector
from pncp_shared.utils.funcoespncp import *
from pncp_bot_obra.crawlers.crawler_pncp import crawler
from pncp_shared.database.repositoriopncp import retornar_plataformas, retornar_paginas, retornar_usuarios
from pncp_shared.config.controle_config import carregar_configuracoes, config

# Para gerar executável:
# pyinstaller controle_banco.py --add-data="controle.html;." --onefile

carregar_configuracoes()

print(retornar_plataformas())

def carregar_plataformas(window):
    plataformas = retornar_plataformas()
    usuarios = retornar_usuarios()
    paginas = []  # retornar_paginas()
    print(plataformas)
    print(paginas)
    print(usuarios)
    window.evaluate_js(f"""
                            var plataformas = {plataformas};
                            var paginas = {paginas};
                            var usuarios = {usuarios};
                            procurarPlataformas();
                            procurarUsuarios();
                        """)


def atualizar_plataforma(id_plat, plataforma_nova, window):
    id_plat = id_plat.strip()
    usuarios = retornar_usuarios()
    print('us', usuarios)
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                 password=config("password"), database=config("database")) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            print(plataforma_nova)
            if id_plat == '':
                cursor.execute(f"INSERT INTO plataformas values(null, '{plataforma_nova['0']['nome']}')")
                cursor.execute('SELECT last_insert_id()')
                id_plat = cursor.fetchone().get('last_insert_id()')
                for url, valor in plataforma_nova['0']['urls'].items():
                    print(url, valor)
                    if url.strip() == "":
                        return "Nao pode inserir tem url vazia"
                    pg = retornar_paginas(url)
                    print('dss', pg)
                    if len(pg) == 0:
                        return "Pagina não encontrada para " + url
                    pg = pg[0]
                    cursor.execute(f"INSERT INTO plataformas_page values(null, {int(id_plat)}, {pg['id']}, null, '', {valor['ativo']})")
                    cursor.execute('SELECT last_insert_id()')
                    id_plat_page = cursor.fetchone().get('last_insert_id()')
                    for id_usuario in usuarios.keys():
                        cursor.execute(
                            f"INSERT INTO plataforma_page_usuarios VALUES (null, {id_plat_page}, {id_usuario}, 1);")
            else:
                plataforma = retornar_plataformas(int(id_plat))
                if plataforma[int(id_plat)]['nome'] != plataforma_nova[id_plat]['nome']:
                    cursor.execute(f"""UPDATE plataformas set descricao = '{plataforma_nova[id_plat]['nome']}'
                                       WHERE plataformas.id = {int(id_plat)}""")

                for v, k in plataforma_nova[id_plat]['urls'].items():
                    url = v.strip()
                    if url == "":
                        return "Uma pagina não contém url"

                    pg = retornar_paginas(v)
                    if len(pg) == 0:
                        return "Pagina não encontrada para " + url
                    pg = pg[0]

                    print(pg)
                    print(v, k)
                    url_banco = plataforma[int(id_plat)]['urls'].get(url, False)
                    print('banco', url_banco)
                    if not url_banco:
                        # Adicionar
                        cursor.execute(f"INSERT INTO plataformas_page values(null, {int(id_plat)}, {pg['id']}, null, '', {k['ativo']})")
                        cursor.execute('SELECT last_insert_id()')
                        id_plat_page = cursor.fetchone().get('last_insert_id()')
                        for id_usuario in usuarios.keys():
                            cursor.execute(f"INSERT INTO plataforma_page_usuarios VALUES (null, {id_plat_page}, {id_usuario}, 1);")
                    else:
                        if url_banco['ativo'] != k.get('ativo', 'true'):
                            print(f"UPDATE plataformas_page SET is_active = {k.get('ativo', True)} WHERE plataformas_page.id = {url_banco['id_plataforma_page']}")
                            cursor.execute(f"UPDATE plataformas_page SET is_active = {k.get('ativo', True)} WHERE plataformas_page.id = {url_banco['id_plataforma_page']}")

                for v, k in plataforma[int(id_plat)]['urls'].items():
                    url = v.strip()
                    if not plataforma_nova[id_plat]['urls'].get(url, False):
                        print('Remover', k, v)
                        print(f"DELETE FROM plataforma_page_usuarios WHERE plataforma_page_usuarios.id_pataforma_pages IN (select id from plataformas_page where plataformas_page.id = {k['id_plataforma_page']})")
                        cursor.execute(f"DELETE FROM plataforma_page_usuarios WHERE plataforma_page_usuarios.id_pataforma_pages IN (select id from plataformas_page where plataformas_page.id = {k['id_plataforma_page']})")
                        cursor.execute(f"DELETE FROM plataformas_page WHERE plataformas_page.id = {k['id_plataforma_page']}")
                        pass

        conexao.commit()

    carregar_plataformas(window)


def apagar_plataforma(id_plataforma):
    id_plataforma = int(id_plataforma)
    plataforma = retornar_plataformas(id_plataforma)
    with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                 password=config("password"), database=config("database")) as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            for url, valor_url in plataforma[id_plataforma]['urls'].items():
                cursor.execute(f"Select * from processos where id_page = {valor_url['id_page']} limit 1")
                retorno = cursor.fetchall()
                print(retorno)
                #if len(retorno) > 0:
                    #return "Nao pode apagar a plataforma pq tem registro nos processos"

                cursor.execute(
                    f"DELETE FROM plataforma_page_usuarios WHERE plataforma_page_usuarios.id_pataforma_pages IN (select id from plataformas_page where plataformas_page.id = {valor_url['id_plataforma_page']})")
                cursor.execute(f"DELETE FROM plataformas_page WHERE plataformas_page.id = {valor_url['id_plataforma_page']}")
            print(plataforma)

            cursor.execute(f"DELETE FROM plataformas WHERE id = {id_plataforma}")
            conexao.commit()

    carregar_plataformas(window)


def atualizar_usuario(id_usu, usuario_novo, window):


    carregar_plataformas(window)


def js(window):
    carregar_plataformas(window)


class Api:
    def gravarInstrucao(self, id_plataforma_page, instrucao_alterada):
        instrucao_alterada = instrucao_alterada.replace("\n", "\\n")
        with mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                     password=config("password"), database=config("database")) as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""update plataformas_page set referencia_codigo = %s where id = {id_plataforma_page}""",
                               (instrucao_alterada, ))
            conexao.commit()

    def testarInstrucao(self, url, instrucao):
        filtros = {'palavraschave': {'segur': ["seguranca", "seguramente", "seguracao", "segurador", "segure", "segurelha", "segureza", "segurelhal", "seguro desemprego", "seguro dpvat", "segurancadepartamento", "seguro social", "segurancaabertura", "seguro obrigatorio"], 'aeronautic': []}}
        filtros['data_inicial'] = formatar_data(datetime(2022, 1, 1), padrao="formatado_br")
        filtros['data_final'] = formatar_data(datetime(2022, 1, 3), padrao="formatado_br")
        instrucao = instrucao.replace("&nbsp;", " ")

        while True:
            crawler(url=url, instrucoes=instrucao, filtros=filtros, mostrar_browser=True, modo_debug=window)

    #def pararDebug(self):
        #parar_debug()

    def atualizarPlataforma(self, id_plat, plataforma_nova):
        print('p', plataforma_nova)
        return atualizar_plataforma(id_plat, plataforma_nova, window)

    def apagarPlataforma(self, id_plataforma):
        return apagar_plataforma(id_plataforma)


if __name__ == '__main__':
    window = webview.create_window('Controle', 'controlenew.html', js_api=Api(), height=680, width=1000, y=0)
    webview.start(func=js, args=window, debug=False)


#print(atualizar_plataforma('2', {'2': {'id_plataforma': '2', 'nome': 'bll', 'urls': {'https://bllcompras.com/Process/ProcessSearchPublic?param1=6': {'ativo': 'false'}, 'https://bllcompras.com/Process/ProcessSearchPublic?param1=4': {'ativo': 'true'}, 'https://bllcompras.com/Process/ProcessSearchPublic?param1=3': {'ativo': 'true'}, 'https://bllcompras.com/Process/ProcessSearchPublic?param1=1': {'ativo': 'true'}}}}))
