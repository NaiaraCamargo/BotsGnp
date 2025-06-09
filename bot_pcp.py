from controle_botold import bot

instrucoes = """
XPATH|LIMPARTEXTO|DIVIDIRTEXTO|NOME; //*[@id="pesquisa-processo-page"]/div/main/section[3]/div/div[2]/span|l2|-0-|Heuristica; FiltrarValor
Heuristica; ; Validacao
Termos; banco; Loop
    FILTROS; objeto=banco[palavrachave]|dataInicial=banco[data_inicial]|dataFinal=banco[data_final]|tipoData=2; AlterarUrl
    ProximaPagina; Url[pagina]; Loop
        CLASS_NAME; lista-processos ; ProcurarElemento
            CLASS_NAME; item; ProcurarElementos
                CLASS_NAME; main-item; ProcurarElemento
                    TAG_NAME|TAG_NAME|NOME; h2|span|Numero; FiltrarValor
                    CLASS_NAME; info; ProcurarElemento
                        TAG_NAME; span; ProcurarElementoChild
                            NOME; Data; FiltrarValorIndex
                            NOME; Licitacao; FiltrarValorIndex
                            NOME; Orgao; FiltrarValorIndex
                            INNERCONTEM; ico-cp cp-pin-mapa verde; ProcurarElemento
                                NOME; Municipio; FiltrarValor
                                EXTRAIRTEXTO|NOME; -:|Uf; FiltrarValor
                    CSS_SELECTOR|VATRIBUTO|NOME; a|href|Link; ProcurarElemento
                    TAG_NAME|NOME|FILTRO; a|Descricao|Banco; FiltrarValor
                CLASS_NAME|TAG_NAME|NOME; aside-item|p|Situacao; FiltrarValor
                ;; EnviarNotificacao

"""


bot('pcp', mostrar_browser=False)
