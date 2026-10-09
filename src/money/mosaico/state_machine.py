"""Macchina a stati dell'hedge group (§7) e invarianti non negoziabili.

Le transizioni sono pure: dato lo stato attuale e un evento, quale stato segue e se
l'evento e' ammesso. Nessun I/O. Le invarianti non negoziabili di §302-309 sono qui
come ECCEZIONI APPLICATIVE (mai `assert`: con `python -O` sparirebbero).
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

# --- stati (§7) --------------------------------------------------------------------
STATI_NORMALI = (
    "CANDIDATE", "ECONOMICALLY_VALIDATED", "PREFLIGHTED",
    "LEG_A_WORKING", "LEG_A_PARTIAL", "LEG_A_FILLED",
    "LEG_B_WORKING", "HEDGED", "MONITORING",
    "EXIT_REQUESTED", "EXIT_LEG_A", "EXIT_LEG_B", "FLAT_VERIFIED",
)
STATI_INCIDENTE = (
    "RECOVERY_REQUIRED", "RECONCILIATION_MISMATCH", "UNWIND_REQUIRED",
    "KILL_SWITCHED", "MANUAL_REVIEW",
)
STATI = STATI_NORMALI + STATI_INCIDENTE

#: Transizioni ammesse: (da, evento) -> a. Tutto cio' che non e' qui e' VIETATO.
TRANSAZIONI: Dict[Tuple[str, str], str] = {
    ("CANDIDATE", "valida_economia"): "ECONOMICALLY_VALIDATED",
    ("ECONOMICALLY_VALIDATED", "preflight_ok"): "PREFLIGHTED",
    ("PREFLIGHTED", "invia_gamba_a"): "LEG_A_WORKING",
    ("LEG_A_WORKING", "fill_parziale"): "LEG_A_PARTIAL",
    ("LEG_A_WORKING", "fill_completo"): "LEG_A_FILLED",
    ("LEG_A_PARTIAL", "fill_completo"): "LEG_A_FILLED",
    ("LEG_A_FILLED", "invia_gamba_b"): "LEG_B_WORKING",
    ("LEG_B_WORKING", "fill_completo_b"): "HEDGED",
    ("HEDGED", "monitora"): "MONITORING",
    ("MONITORING", "richiedi_uscita"): "EXIT_REQUESTED",
    ("EXIT_REQUESTED", "chiudi_a"): "EXIT_LEG_A",
    ("EXIT_LEG_A", "chiudi_b"): "EXIT_LEG_B",
    ("EXIT_LEG_B", "verifica_piatto"): "FLAT_VERIFIED",
    # incidenti
    ("LEG_A_WORKING", "gamba_b_non_coperta"): "UNWIND_REQUIRED",
    ("LEG_A_FILLED", "gamba_b_non_coperta"): "UNWIND_REQUIRED",
    ("LEG_B_WORKING", "gamba_b_non_coperta"): "UNWIND_REQUIRED",
    ("UNWIND_REQUIRED", "verifica_piatto"): "FLAT_VERIFIED",
    ("MONITORING", "mismatch"): "RECONCILIATION_MISMATCH",
    ("MONITORING", "rischio"): "KILL_SWITCHED",
    ("*", "mismatch_globale"): "RECONCILIATION_MISMATCH",
    ("*", "kill"): "KILL_SWITCHED",
}

#: Stati da cui NON si entra mai una nuova volta (terminali).
TERMINALI: FrozenSet[str] = frozenset({"FLAT_VERIFIED", "KILL_SWITCHED", "MANUAL_REVIEW"})

#: Stati d'incidente che BLOCCANO nuove entrate (§303).
BLOCCANTI: FrozenSet[str] = frozenset({"RECOVERY_REQUIRED", "RECONCILIATION_MISMATCH",
                                       "UNWIND_REQUIRED", "KILL_SWITCHED"})


class TransizioneVietata(Exception):
    """Una transizione non ammessa dalla macchina di §7. Mai silenziosa."""


def transizione(stato: str, evento: str) -> str:
    """Quale stato segue. Solleva se la coppia non e' ammessa."""
    if stato in TERMINALI:
        raise TransizioneVietata(f"stato terminale {stato}: nessuna transizione ammessa")
    if (stato, evento) in TRANSAZIONI:
        return TRANSAZIONI[(stato, evento)]
    if ("*", evento) in TRANSAZIONI:
        return TRANSAZIONI[("*", evento)]
    raise TransizioneVietata(f"transizione vietata: {stato} + {evento}")


def puo_entrare(stato: str) -> bool:
    """Niente nuova entrata in uno stato bloccante (§303)."""
    return stato not in BLOCCANTI and stato not in TERMINALI


def verifica_invarianti(*, stato: str, delta_relativo: float,
                        delta_max_normale: float, delta_max_duro: float,
                        saldo_locale_riconciliato: bool, retry_riusa_intent: bool,
                        posizione_confermata_exchange: bool) -> None:
    """Controlla le invarianti non negoziabili di §302-309.

    Solleva `TransizioneVietata` (eccezione applicativa) con il motivo esatto.
    """
    if delta_relativo > delta_max_duro:
        # §305: delta oltre la soglia dura -> uscita d'emergenza, non prosecuzione.
        raise TransizioneVietata(
            f"delta {delta_relativo:.4%} oltre la soglia DURA {delta_max_duro:.4%}: uscita richiesta")
    if not saldo_locale_riconciliato:
        # §304: niente seconda gamba calcolata da un saldo locale non riconciliato.
        raise TransizioneVietata(
            "saldo locale non riconciliato: la seconda gamba non si calcola da qui")
    if not retry_riusa_intent:
        # §306: ogni retry riusa lo stesso intent_id.
        raise TransizioneVietata("retry senza lo stesso intent_id: rischio di ordine duplicato")
    if not posizione_confermata_exchange:
        # §307: una posizione aperta non e' chiusa finche' l'exchange non lo conferma.
        raise TransizioneVietata(
            "posizione non confermata dall'exchange: non si puo' dichiarare chiuso")


def scenario_stato(stato: str) -> str:
    """Classifica lo stato: 'normale', 'incidente', 'terminale'."""
    if stato in TERMINALI:
        return "terminale"
    if stato in STATI_INCIDENTE:
        return "incidente"
    return "normale"
