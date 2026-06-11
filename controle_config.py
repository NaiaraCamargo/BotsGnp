import json
import os
from time import sleep

usuariosNotificar = []
configuracoes = {
    "token_telegram": "",
    "token_telegram_alterados": "",
    "dias_limpar_logs": 30,
    "conexao_banco": {
        "host": "",
        "port": 3306,
        "user": "",
        "password": "",
        "database": ""
    },
    "UNRAR_TOOL":"",
    "path_wkhtmltoimage": "",
    "pasta_downloads": "",
    "raiz_local": "",
    "raiz_server": "",
    "extensoes_imgs": [],
    "extensoes_planilhas": [],
    "formatos_para_docx": [],
    "extensoes_validas": [],
    "limite_kb": 10000,
    "processar_todos_obra": False,
    "processar_todos_pintura": False,
    "processar_todos_reforma": False,
    "processar_todos_projeto_arquitetonico": False,
    "processar_todos_asbuilt": False,
    "processar_todos_construcao": False,
    "processar_todos_poco_artesiano": False,
    "processar_dia": True,
}

CAMINHO_CONFIG = "config.json"

def carregar_configuracoes():
    global configuracoes

    try:
        if os.path.isfile(CAMINHO_CONFIG):
            with open(CAMINHO_CONFIG, "r", encoding="utf-8") as f:
                carregado = json.load(f)
                configuracoes.update(carregado)
        else:
            with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
                json.dump(configuracoes, f, indent=4)
            raise Exception(f"Arquivo '{CAMINHO_CONFIG}' criado. Configure os valores antes de continuar.")
        sleep(1)
    except Exception as e:
        print("Erro ao carregar configurações:", e)
        raise


def atualizar_arquivo_configuracoes():
    try:
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(configuracoes, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print("Erro ao salvar configurações:", e)
        raise


def config(nome, texto=True):
    if nome in configuracoes["conexao_banco"]:
        return str(configuracoes["conexao_banco"][nome]) if texto else configuracoes["conexao_banco"][nome]
    elif nome in configuracoes:
        return str(configuracoes[nome]) if texto else configuracoes[nome]
    else:
        print(f"Configuração '{nome}' não encontrada.")
        return None