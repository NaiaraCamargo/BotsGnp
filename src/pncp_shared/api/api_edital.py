from datetime import datetime
from decimal import Decimal

from pncp_shared.logs.controle_logs import logs
from pncp_shared.utils.funcoespncp import limpar_para_mysql, formatar_valor_sigilo


def _campo_ausente(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _formatar_valor_api(valor):
    numero = Decimal(str(valor))
    if not numero.is_finite() or numero < 0:
        raise ValueError(f'Valor monetario invalido na consulta: {valor!r}')
    return formatar_valor_sigilo(numero)


def montar_complementos_compra(compra, edital):
    campos = {
        'LinkBotao': compra.get('linkSistemaOrigem'), 'ValorTotalHomologado': compra.get('valorTotalHomologado'), }
    complementos = {}
    for campo, valor in campos.items():
        if not _campo_ausente(edital.get(campo)) or _campo_ausente(valor):
            continue
        elif campo in {'ValorTotalEstimadoCompra', 'ValorTotalHomologado'}:
            valor = _formatar_valor_api(valor)
        elif campo == 'Descricao':
            valor = limpar_para_mysql(valor)
        complementos[campo] = valor
        
    return complementos

def montar_itens_campos(link: str, itens: list[dict]) -> list[dict]:
    try:
        campos_itens = []

        for item in (itens or []):
            numero = item.get("numeroItem")
            descricao = item.get("descricao")
            quantidade = item.get("quantidade")
            valor_unit = item.get("valorUnitarioEstimado") or item.get("valorUnitario")
            valor_total = item.get("valorTotalEstimado") or item.get("valorTotal")
            
            campos_itens.append({
                "numeroItem": numero,
                "descricaoItem": descricao,
                "quantidadeItem": quantidade,
                "valorUnitItem": valor_unit,
                "valorTotalItem": valor_total,
            })

        return campos_itens

    except Exception as e:
        logs.error(f"[ERRO AO MONTAR ITENS API] {link} - {e}")
        return []
