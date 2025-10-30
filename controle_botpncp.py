from concurrent.futures import ThreadPoolExecutor
from sys import argv
import threading
import time
from crowlerpncp import *
from repositoriopncp import *
from gerar_planilha import *
from funcoespncp import *

def rodar_crawler_thread(url: str, filtros_locais: dict, notificacao_config: dict,
                         mostrar_browser: bool):
    crawler(url, filtros=filtros_locais, notificacao_config=notificacao_config,
            mostrar_browser=mostrar_browser)


def executar_url(url: str, dados_url: dict, plataforma: str, filtros: dict,
                 mostrar_browser: bool, data_inicial: str, data_final: str, format_data: str):

    match = re.search(r'[?&]q=([^&]+)', url)
    palavra_chave = match.group(1) + '*' if match else ''
    
    if dados_url['id_pagina'] == 13215:
        palavra_chave = 'projeto_arquitetonico*'
    elif dados_url['id_pagina'] == 13217:
        palavra_chave = 'construcao*'
    elif dados_url['id_pagina'] == 13218:
        palavra_chave = 'poco_artesiano*'
            
    filtros_locais = {
        'banco': {
            'palavraschave': retornar_dicionario_filtros(palavra_chave),
            'ultima_data': formatar_data(dados_url.get('ultima_data', ''), padrao=format_data)
        }
    }

    filtros_locais['banco'].update({
        "data_inicial": data_inicial or filtros_locais['banco']["ultima_data"],
        "data_final": data_final or formatar_data(limpar=False, padrao=format_data),
        "qtd_registros": dados_url.get("qtd_registros", 0)
    })

    notificacao_config = {
        'id_pagina': dados_url['id_pagina'],
        'ids_usuarios': dados_url['ids_usuario'],
        'plataforma': plataforma,
        'primeira_execucao': not dados_url.get("ultima_data", '')
    }

    thread = threading.Thread(target=rodar_crawler_thread, args=(
        url, filtros_locais, notificacao_config, mostrar_browser))
    thread.start()
    thread.join()


def bot(plataforma: str, url: str = '', filtros: dict = {}, mostrar_browser: bool = False,
        rodar_infinito: bool = True, data_inicial: str = "", data_final: str = "", format_data: str = "universal"):

    execucoes = 1

    while True:
        try:
            limpar_console()
            carregar_configuracoes()
            controle_logs(f"{plataforma}-new")
            urls = retornar_urls(plataforma)

            if not urls:
                print(f"Nenhuma plataforma localizada para {plataforma}")
                time.sleep(5)
                continue

            with ThreadPoolExecutor(max_workers=5) as executor:
                for url_item, dados_url in urls.items():
                    executor.submit(
                        executar_url,
                        url_item,
                        dados_url,
                        plataforma,
                        filtros,
                        mostrar_browser,
                        data_inicial,
                        data_final,
                        format_data
                    )

            execucoes += 1
            if not rodar_infinito:
                break

        except Exception as e:
            logs.exception("Erro no bot principal. Reiniciando em 10 segundos...")
            time.sleep(10)


def processar_url_alteracoes(plataforma: str):
    try:
        while True:
            limpar_console()
            plat = f"{plataforma}-alteracoes"
            controle_logs(plat)
            carregar_configuracoes()
            urls = retornar_urls(plataforma)

            ids = []
            notificacao_config = {}

            for url_item, dados_url in urls.items():
                idpagina = dados_url['id_pagina']
                ids.append(idpagina)
                notificacao_config[idpagina] = {
                    'id_pagina': idpagina,
                    'ids_usuarios': dados_url['ids_usuario'],
                    'plataforma': plataforma,
                    'url': url_item,
                }

            data_inicial_conf = configuracoes.get('data_inicial', None)
            lista_processos = retorna_processos_banco(ids, data_inicial_conf)
            processos_planilha = []

            for processo in lista_processos:
                try:
                    idpagina = processo['id_page']
                    retorno = None

                    if idpagina in notificacao_config:
                        retorno = executar_processos_alteracao(processo, notificacao_config[idpagina])

                    if retorno:
                        processos_planilha.append(retorno)
                    else:
                        atualizar_ultima_data(idpagina)
                        logs.info("O retorno executar_processos_alteracao retornou None")

                except Exception as e:
                    logs.exception(f"Erro ao processar processo: {processo}")

            if processos_planilha:
                gerar_excel_registros(processos_planilha, plataforma, False)

            # Pode ajustar para rodar de tempos em tempos em vez de loop infinito direto
            time.sleep(300)

    except Exception as e:
        logs.exception("Erro ao processar alterações")

if __name__ == '__main__':
    print(len(argv))
    '''if len(argv) > 1:
        if len(argv) == 3:
            bot(argv[1], argv[2])
        elif len(argv) == 4:
            argv[3] = argv[3].lower()
            primeira_exe = False
            if argv[3] == "true" or argv[3] == "t" or argv[3] == "1":
                primeira_exe = True
            bot(argv[1], argv[2], primeira_exe)'''