import json
import sys
from pathlib import Path
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
    "UNRAR_TOOL": "",
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

    "email_planilha_botbool": {
        "email_remetente": "",
        "senha_email": "",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587
    }
}


PACOTES_CONFIG = {
    "obra": "pncp_bot_obra",
    "seguro": "pncp_bot_seguro",
    "material_escolar": "pncp_bot_material_escolar",
}


def pacote_por_plataforma(plataforma):
    plataforma = str(plataforma or "").strip().lower()

    if plataforma in PACOTES_CONFIG:
        return PACOTES_CONFIG[plataforma]

    if plataforma in PACOTES_CONFIG.values():
        return plataforma

    raise ValueError(f"Plataforma inválida: {plataforma}")


def caminho_base_pacote(nome_pacote):
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / nome_pacote

    # controle_config.py está em:
    # src/pncp_shared/config/controle_config.py
    #
    # parents[0] = config
    # parents[1] = pncp_shared
    # parents[2] = src
    return Path(__file__).resolve().parents[2] / nome_pacote


def caminho_config(plataforma=None, nome_pacote=None):
    if plataforma:
        nome_pacote = pacote_por_plataforma(plataforma)
    elif nome_pacote:
        nome_pacote = pacote_por_plataforma(nome_pacote)
    else:
        raise ValueError("Informe a plataforma ou o nome_pacote para localizar o config.json.")

    return caminho_base_pacote(nome_pacote) / "config.json"


def carregar_configuracoes(plataforma=None, nome_pacote=None):
    global configuracoes

    try:
        caminho = caminho_config(
            plataforma=plataforma,
            nome_pacote=nome_pacote
        )

        if caminho.is_file():
            with open(caminho, "r", encoding="utf-8") as f:
                carregado = json.load(f)
                configuracoes.update(carregado)
        else:
            caminho.parent.mkdir(parents=True, exist_ok=True)

            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(configuracoes, f, indent=4, ensure_ascii=False)

            raise Exception(f"Arquivo '{caminho}' criado. Configure os valores antes de continuar.")

        sleep(1)

    except Exception as e:
        print("Erro ao carregar configurações:", e)
        raise


def atualizar_arquivo_configuracoes(plataforma=None, nome_pacote=None):
    try:
        caminho = caminho_config(
            plataforma=plataforma,
            nome_pacote=nome_pacote
        )

        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(configuracoes, f, indent=4, ensure_ascii=False)

    except Exception as e:
        print("Erro ao salvar configurações:", e)
        raise


def config(nome, texto=True):
    if nome in configuracoes.get("conexao_banco", {}):
        valor = configuracoes["conexao_banco"][nome]
        return str(valor) if texto else valor

    if nome in configuracoes:
        valor = configuracoes[nome]
        return str(valor) if texto else valor

    print(f"Configuração '{nome}' não encontrada.")
    return None