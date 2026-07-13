from concurrent.futures import ThreadPoolExecutor
from sys import argv
import threading
import time
from pncp_shared.database.repositoriopncp import *
from pncp_shared.database.backup_bancos import executar_backup_se_necessario
from pncp_shared.utils.funcoespncp import *
from pncp_shared.logs.controle_logs import *
from pncp_shared.config.controle_config import *
from pncp_bot_seguro.crawlers.crawler_pncp import *

_backup_lock = threading.Lock()

def iniciar_backup_banco_periodico(plataforma):
    if _backup_lock.locked():
        return

    def rotina_backup():
        with _backup_lock:
            try:
                dias_intervalo = int(configuracoes.get("dias_intervalo_bkp", 2))
                resultado = executar_backup_se_necessario(
                    plataforma=plataforma,
                    dias_intervalo=dias_intervalo,
                )
                if resultado.status == "erro":
                    logs.error(resultado.mensagem)
            except Exception as e:
                logs.exception(f"Erro ao executar backup do banco ({plataforma}): {e}")

    threading.Thread(target=rotina_backup, daemon=True).start()


def rodar_crawler_thread(url: str, filtros_locais: dict, notificacao_config: dict,
                         mostrar_browser: bool):
    crawler(url, filtros=filtros_locais, notificacao_config=notificacao_config,
            mostrar_browser=mostrar_browser)


def executar_url(url: str, dados_url: dict, plataforma: str, filtros: dict,
                 mostrar_browser: bool, data_inicial: str, data_final: str, format_data: str):

    match = re.search(r'[?&]q=([^&]+)', url)
    palavra_chave = match.group(1) + '*' if match else ''
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
            carregar_configuracoes(plataforma)
            controle_logs()
            iniciar_backup_banco_periodico(plataforma)
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
