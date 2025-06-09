from controle_botold import bot

instrucoes = """
; ShowAdvFields(); ExecutarScript
; document.getElementById('fkStatus').value = ''; ExecutarScript
; document.getElementById('fkModality').value = ''; ExecutarScript
NAME; DateStart; ProcurarElemento
    ; banco[data_inicial]; DefinirValor
NAME; DateEnd; ProcurarElemento
    ; banco[data_final]; DefinirValor
; ProcessSearch() ; ExecutarScript
ID; tableProcessDataBody; ProcurarElemento
    TAG_NAME; tr; ProcurarElementos
        TAG_NAME; td; ProcurarElemento 
            NOME; Orgao; FiltrarValorIndex1
            NOME; Numero; FiltrarValorIndex2
            NOME; Municipio; FiltrarValorIndex4
            EXTRAIRTEXTO|NOME; -:|Uf; FiltrarValorIndex4
            NOME; Situacao; FiltrarValorIndex5
            NOME; Data; FiltrarValorIndex6
            NOME; DataDisputa; FiltrarValorIndex7
            Buffer; ContagemControle; Validacao
            TAG_NAME|NOME; a[href]|Link; FiltrarValorIndex0
            NovaGuia; ValorArmazenado[Link]; Click
                XPATH|FILTRO|NOME; //textarea[@id='ProductOrService']|Banco|Descricao; FiltrarValor
                NOME|XPATH; Licitacao|//input[@id='ContractKind']; FiltrarValor
                NOME|XPATH; NmrProcessoAdministrativo|//input[@id='AdmNumber']; FiltrarValor
                NOME|XPATH; Condutor|//input[@id='Conductor']; FiltrarValor
                NOME|XPATH; InicioRecebimentoProposta|//input[@id='ProposalReceivingStart']; FiltrarValor
                NOME|XPATH; FimRecebimentoProposta|//input[@id='ProposalAnalysisStart']; FiltrarValor
                NOME|XPATH; InicioDisputa|//input[@id='DisputeStart']; FiltrarValor
                NOME|XPATH; ModoDisputa|//input[@id='ClosingKind']; FiltrarValor               
                NOME|XPATH; ValorTotalProcesso|//input[@id='TotalBaseValue']; FiltrarValor
                NOME|XPATH; FonePromotor|//input[@id='OrgPhone']; FiltrarValor
                NOME|XPATH; EmailPromotor|//input[@id='OrgEmail']; FiltrarValor
                ;; EnviarNotificacao
"""

# para o directbuy

"""
; document.getElementById('fkStatus').value = ''; ExecutarScript
NAME; DateStart; ProcurarElemento
    ; banco[data_inicial]; DefinirValor
NAME; DateEnd; ProcurarElemento
    ; banco[data_final]; DefinirValor
; DirectBuySearch() ; ExecutarScript
ID; tableDirBuyDataBody; ProcurarElemento
    TAG_NAME; tr; ProcurarElementos
        TAG_NAME; td; ProcurarElemento
            NOME; Orgao; FiltrarValorIndex1
            NOME; Numero; FiltrarValorIndex2
            NOME; Municipio; FiltrarValorIndex1
            NOME; Situacao; FiltrarValorIndex3
            NOME; Modalidade; FiltrarValorIndex4
            NOME; Data; FiltrarValorIndex5
            NOME; DataDisputa; FiltrarValorIndex6
            Buffer; ; Validacao
            TAG_NAME|NOME; a[href]|Link; FiltrarValorIndex0
            NovaGuia; ValorArmazenado[Link]; Click
                XPATH|FILTRO|NOME; //textarea[@id='ProductOrService']|Banco|Descricao; FiltrarValor
                NOME|XPATH; NmrProcessoAdministrativo|//input[@id='AdmNumber']; ProcurarElemento
                NOME|XPATH; Condutor|//input[@id='ConductorName']; ProcurarElemento

"""


bot(plataforma='bll',
    mostrar_browser=False,
    format_data="formatado_br"
)
