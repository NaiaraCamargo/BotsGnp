from __future__ import annotations

from collections.abc import Iterable

from pncp_shared.utils.funcoespncp import converter_moeda_brl_para_float


CODIGOS_BOT = frozenset({"GNP", "BOOL", "EDIT"})


def normalizar_codigo_bot(codigo: str) -> str:
    codigo_normalizado = str(codigo or "").strip().upper()
    if codigo_normalizado not in CODIGOS_BOT:
        raise ValueError(f"Codigo de bot invalido: {codigo!r}")
    return codigo_normalizado


def normalizar_destinos(destinos: Iterable[str] | str | None) -> set[str]:
    if destinos is None:
        return set()

    if isinstance(destinos, str):
        destinos = destinos.split(",")

    return {
        codigo
        for valor in destinos
        if (codigo := str(valor or "").strip().upper()) in CODIGOS_BOT
    }


def calcular_destinos_aprovados(edital: dict, destinos_pagina: Iterable[str] | str | None, edit_valido: bool = False) -> set[str]:
    destinos = normalizar_destinos(destinos_pagina)
    aprovados: set[str] = set()

    uf = str(edital.get("Uf", "")).strip().upper()
    valor_total = str(edital.get("ValorTotalEstimadoCompra", "")).strip().upper()
    valor_sigiloso = valor_total == "SIGILOSO"
    valor_estimado = 0 if valor_sigiloso else converter_moeda_brl_para_float(valor_total)

    if "GNP" in destinos and uf in {"RS", "SC"}:
        aprovados.add("GNP")

    if "BOOL" in destinos and (valor_estimado > 500000 or valor_sigiloso):
        aprovados.add("BOOL")

    if "EDIT" in destinos and edit_valido:
        aprovados.add("EDIT")

    return aprovados


def destinatarios_por_destino(destinatarios: list[dict], destino: str) -> list[str]:
    destino = normalizar_codigo_bot(destino)
    ids: list[str] = []

    for destinatario in destinatarios or []:
        id_telegram = str(destinatario.get("id_telegram") or "").strip()
        codigo_destino = str(destinatario.get("codigo_destino") or "").strip().upper()

        if not id_telegram:
            continue

        # Usuario sem destino ainda nao esta configurado para este fluxo.
        if codigo_destino == destino:
            if id_telegram not in ids:
                ids.append(id_telegram)

    return ids
