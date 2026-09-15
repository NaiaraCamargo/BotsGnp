import json
import errno
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from email.utils import parsedate_to_datetime

import requests

from pncp_shared.logs.controle_logs import logs


INTERVALO_MINIMO_SEG = 3.1
ESPERA_PROGRESSIVA_BASE_SEG = 10
MAX_TENTATIVAS = 3
STATUS_RETENTATIVA = {429, 500, 502, 503, 504}
INTERVALO_ESPERA_LOCK_SEG = 0.2
_lock_thread = threading.Lock()
_arquivo_lock = os.path.join(tempfile.gettempdir(), "gnp_pncp_rate_limit.lock")


def _bloquear_arquivo(arquivo):
    if os.name == "nt":
        import msvcrt

        while True:
            arquivo.seek(0)
            try:
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as erro:
                codigos_ocupado = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
                if erro.errno not in codigos_ocupado and getattr(erro, "winerror", None) not in {32, 33}:
                    raise
                time.sleep(INTERVALO_ESPERA_LOCK_SEG)
    else:
        import fcntl
        arquivo.seek(0)
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX)


def _desbloquear_arquivo(arquivo):
    arquivo.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)


@contextmanager
def _abrir_arquivo_bloqueado():
    with _lock_thread:
        with open(_arquivo_lock, "a+b") as arquivo:
            _bloquear_arquivo(arquivo)
            try:
                yield arquivo
            finally:
                _desbloquear_arquivo(arquivo)


def _ler_estado(arquivo):
    arquivo.seek(0)
    conteudo = arquivo.read().decode("utf-8", errors="ignore").strip()

    try:
        estado = json.loads(conteudo)
        if not isinstance(estado, dict):
            raise TypeError
        return {"ultima_chamada": float(estado.get("ultima_chamada") or 0),
                "bloqueado_ate": float(estado.get("bloqueado_ate") or 0)}
    except (TypeError, ValueError, json.JSONDecodeError):
        try:
            return {"ultima_chamada": float(conteudo or 0), "bloqueado_ate": 0}
        except ValueError:
            return {"ultima_chamada": 0, "bloqueado_ate": 0}


def _salvar_estado(arquivo, estado):
    arquivo.seek(0)
    arquivo.truncate()
    arquivo.write(json.dumps(estado, separators=(",", ":")).encode("utf-8"))
    arquivo.flush()


def _segundos_retry_after(response):
    valor = response.headers.get("Retry-After")
    if not valor:
        return 0

    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        try:
            data = parsedate_to_datetime(valor)
            return max(0, int(data.timestamp() - time.time()))
        except Exception:
            return 0


def _calcular_espera(tentativa, response=None):
    progressiva = ESPERA_PROGRESSIVA_BASE_SEG * (2 ** (tentativa - 1))
    if response is None:
        return progressiva

    retry_after = _segundos_retry_after(response)
    bloqueio_pncp = 40 if response.status_code == 429 else 0
    return max(retry_after, progressiva, bloqueio_pncp)


def _reservar_inicio_global():
    while True:
        with _abrir_arquivo_bloqueado() as arquivo:
            estado = _ler_estado(arquivo)
            agora = time.time()
            espera_intervalo = INTERVALO_MINIMO_SEG - (agora - estado["ultima_chamada"])
            espera_bloqueio = estado["bloqueado_ate"] - agora
            espera = max(0, espera_intervalo, espera_bloqueio)

            if espera <= 0:
                estado["ultima_chamada"] = time.time()
                _salvar_estado(arquivo, estado)
                return

        time.sleep(espera)


def _publicar_bloqueio_global(segundos):
    with _abrir_arquivo_bloqueado() as arquivo:
        estado = _ler_estado(arquivo)
        estado["bloqueado_ate"] = max(estado["bloqueado_ate"], time.time() + max(0, segundos))
        _salvar_estado(arquivo, estado)


def _executar_requisicao_global(method, url, tentativa, **kwargs):
    """Espaca o inicio das chamadas e compartilha cooldown entre processos locais."""
    _reservar_inicio_global()
    try:
        response = requests.request(method, url, **kwargs)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        _publicar_bloqueio_global(_calcular_espera(tentativa))
        raise

    if response.status_code in STATUS_RETENTATIVA:
        _publicar_bloqueio_global(_calcular_espera(tentativa, response))

    return response


def executar_navegacao_pncp(operacao):
    """Reserva um inicio global e libera os demais bots durante a navegacao Selenium."""
    _reservar_inicio_global()
    return operacao()


def requisicao_pncp(method, url, *, max_tentativas=MAX_TENTATIVAS, **kwargs):
    """Executa chamada PNCP com limite de inicio e espera progressiva global."""
    ultimo_erro = None

    for tentativa in range(1, max_tentativas + 1):
        try:
            response = _executar_requisicao_global(method, url, tentativa, **kwargs)

            if response.status_code not in STATUS_RETENTATIVA or tentativa == max_tentativas:
                return response

            espera = _calcular_espera(tentativa, response)
            logs.warning(f"[PNCP RETENTATIVA] status={response.status_code} tentativa={tentativa}/{max_tentativas} espera={espera}s url={url}")
            response.close()

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as erro:
            ultimo_erro = erro
            if tentativa == max_tentativas:
                raise

            espera = _calcular_espera(tentativa)
            logs.warning(f"[PNCP RETENTATIVA] erro={type(erro).__name__} tentativa={tentativa}/{max_tentativas} espera={espera}s url={url}")

    if ultimo_erro:
        raise ultimo_erro

    raise requests.exceptions.RequestException(f"Falha inesperada ao requisitar PNCP: {url}")
