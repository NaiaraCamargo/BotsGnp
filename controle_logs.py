import logging
import os
from datetime import datetime, timedelta
import re
from controle_config import *

logs = logging.getLogger('logger1')

def controle_logs():
    global logs

    try:
        hoje = datetime.now()

        if not os.path.isdir("logs"):
            os.makedirs("logs")

        caminho = "logs"

        if logs.hasHandlers():
            logs.handlers.clear()

        logs.setLevel(logging.DEBUG)

        handler1 = logging.FileHandler(
            os.path.join(caminho, f"{hoje.date()}.log"),
            encoding="utf-8"
        )
        handler1.setLevel(logging.DEBUG)
        handler1.setFormatter(
            logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logs.addHandler(handler1)

        dias_limpar_logs = configuracoes.get("dias_limpar_logs", 30)
        menos_dias = (hoje - timedelta(days=dias_limpar_logs)).date()

        for arq in os.listdir(caminho):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.log", arq):
                nome_data = arq[:-4]
                try:
                    data_arquivo = datetime.strptime(nome_data, "%Y-%m-%d").date()
                    if data_arquivo < menos_dias:
                        os.remove(os.path.join(caminho, arq))
                except ValueError:
                    pass

    except Exception as e:
        print(f"Controle Logs: {e}")
        raise