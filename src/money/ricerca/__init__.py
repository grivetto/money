"""money.ricerca — le ipotesi, una per file, misurate con lo stesso rig del live.

REGOLA DEL MODULO
=================
Qui **non** si decide se una strategia e' buona: si produce un `Esito`, e a giudicare e'
`money.cancello`. Nessun file di questo pacchetto puo' promuovere niente da solo, e nessuno
puo' arrotondare un risultato per farlo passare.

Ogni ipotesi e' un file, espone `simula(...) -> Esito` e dichiara nel proprio docstring:
cosa afferma, su quali dati, con quali parametri, e **cosa non dimostra**.
"""
