import asyncio

from pncp_shared.logs.controle_logs import logs


async def executar_com_timeout_suave(corotina, timeout_seg, descricao="job"):
    """Avisa quando exceder o tempo, mas aguarda a thread terminar sem criar execucao orfa."""
    tarefa = asyncio.create_task(corotina)

    try:
        return await asyncio.wait_for(asyncio.shield(tarefa), timeout=float(timeout_seg))
    except asyncio.TimeoutError:
        if tarefa.done():
            return await tarefa

        logs.warning(f"[JOB LONGO] {descricao} excedeu {timeout_seg}s e continua em execucao ate finalizar com seguranca.")
        return await tarefa
