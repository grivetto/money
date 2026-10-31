#!/usr/bin/env python3
"""E15 — «carry funding a soglia su universo perp OKX» — engine deterministico.

Spec congelata: coda_catena/E15_carry_soglia.md (commit 247de15e, lint 7/7, PRIMA dei numeri).
Zero gradi di liberta'. Solo dati congelati (handoff REQ-NUV-20261030-009), nessun accesso rete.

Uso:
    python3 e15_carry_soglia.py --dati-dir <dir> --out-prove <dir>
    exit 0 = misura eseguita; exit 2 = input non validi (fail-closed, nessun numero).

Regola (dalla spec, letterale):
- Segnale giorno t: FA_t = mean_rate(t) * n_epochs(t) * 365 * 100  [%/anno].
- Posizione del giorno d (eseguita all'apertura di d, solo su segnali di d-1 e d-2):
    * ingresso: coppia non in posizione con FA(d-1) >= 10.0;
    * permanenza: in posizione con FA(d-1) >= 5.0 (isteresi) E non(sum_rate(d-2) < 0 e
      sum_rate(d-1) < 0)  [funding negativo per 2 giorni consecutivi -> uscita];
    * FA(d-1) assente (nessun record funding) -> la coppia NON resta in posizione;
    * cap: massimo 5 coppie, le 5 con FA(d-1) piu' alto (tie: instId), applicato DOPO
      entrate/uscite; una coppia ammessa ma tagliata dal cap non paga switch.
- PnL del giorno d = sum(sum_rate(c,d) * nozionale per c in posizione) - switch * nozionale
  * n_entrate(d). Record funding assente per una coppia in posizione: contributo 0 (conteggiato).
- nozionale per coppia = 1000 / (2 * 5) = 100 EUR; capitale vincolato per coppia = 2 * nozionale
  = 200 EUR (spot + margine perp 1x). Capitale di riferimento: 1.000 EUR.
- Switch: 30bp RT base (20bp spot + 10bp perp, taker), 60bp stress. ATTRIBUZIONE DICHIARATA
  (conservativa): l'intero RT e' addebitato al giorno di INGRESSO della coppia; la chiusura
  non aggiunge costi (gia' pagati). Un rientro successivo paga di nuovo il proprio RT.
- NIENTE mark-to-market della basis: l'ipotesi congelata misura il funding netto dopo costi
  (il delta-neutro annulla il prezzo a meno della basis, non inclusa nella spec). Le candele
  1D servono SOLO per l'universo (>=90 bar) e per l'eseguibilita' (bar che copre l'inizio del
  giorno d). Le bar del preflight iniziano alle 16:00 UTC (verificato: first 2025-03-10T16:00Z,
  last 2026-10-30T16:00Z confirm=0) -> condizione di copertura: ts <= day(d) < ts + 24h.
- Finestre: giorni PIENI 2026-07-28..2026-10-30 (95). TRAIN = primi 57 (28/07..22/09),
  OOS = ultimi 38 (23/09..30/10). Il 27/07 (n_epochs=1: cut OKX 16:00Z) e' usato SOLO come
  segnale per il 28/07 (FA su n_epochs=1, dichiarato); il 31/10 (parziale, fuori finestra)
  non e' usato ne' come segnale ne' come misura.
- Exit 2 (fail-closed): dati assenti/malformati, funding_daily vuoto, giorni non consecutivi,
  estremi non parziali, finestra != 95 giorni, duplicati, record non numerici, universo vuoto.

Determinismo: nessun RNG nel run; CI bootstrap con seme fisso 20260101 (money.statistica);
ordinamenti totali (FA desc, tie instId).
"""
import argparse
import hashlib
import json
import math
import os
import sys

_QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_QUI))
from money import statistica as st  # noqa: E402

MS_GIORNO = 86_400_000
CAPITALE = 1000.0                  # EUR, capitale di riferimento
CAP_COPPIE = 5
SOGLIA_IN = 10.0                   # FA % ingresso
SOGLIA_OUT = 5.0                   # FA % uscita (isteresi)
GIORNI_NEG_ESC = 2                 # funding negativo per 2 giorni consecutivi -> uscita
SWITCH_BASE = 0.0030               # RT 30bp (20bp spot + 10bp perp, taker)
SWITCH_STRESS = 0.0060             # RT 60bp (stress x2)
MIN_BAR = 90                       # storia minima spot E perp (bar 1D)
T1_N_MIN = 30
T1_T_MIN = 2.0
T2_MEAN_MIN = 0.0
T3_T_MIN = 1.5
BASELINE_ANNUO = 0.03              # Simple Earn ~3%/anno
N_TENTATIVI_DSR = 2                # soglia 10% e cap 5: due sole configurazioni dichiarate
SEME_CI = 20260101                 # seme fisso CI bootstrap (convenzione repo)
GIORNI_TRAIN = 57
GIORNI_OOS = 38
GIORNI_PIENI = GIORNI_TRAIN + GIORNI_OOS  # 95


def nozionale_per_coppia():
    """Nozionale per coppia: capitale / (2 * cap)."""
    return CAPITALE / (2.0 * CAP_COPPIE)


def capitale_vincolato_per_coppia():
    """Capitale vincolato per coppia: 2 x nozionale (spot + margine perp 1x)."""
    return 2.0 * nozionale_per_coppia()


def capitale_vincolato_totale():
    """Capitale vincolato massimo: cap coppie x 2 x nozionale (== capitale di riferimento)."""
    return CAP_COPPIE * capitale_vincolato_per_coppia()


class DataError(Exception):
    pass


def _num(x, contesto):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise DataError(f'valore non numerico in {contesto}: {x!r}')
    return float(x)


def fa_giorno(riga):
    """FA (funding annualizzato, %/anno) di una riga giornaliera. None se nessuna epoca."""
    n = riga['n_epochs']
    if n <= 0:
        return None
    return riga['mean_rate'] * n * 365.0 * 100.0


def carica_funding(path):
    """Carica funding_daily.json -> {sym: {day: riga}} + giorni globali ordinati.

    Validazioni fail-closed: campi numerici, day allineati alla mezzanotte UTC,
    ordinati e senza duplicati per simbolo, n_epochs >= 1.
    """
    if not os.path.exists(path):
        raise DataError(f'funding_daily.json assente: {path}')
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise DataError(f'funding_daily.json illeggibile: {e}') from e
    if not isinstance(raw, dict) or not raw:
        raise DataError('funding_daily.json vuoto o non oggetto')
    daily = {}
    for sym, righe in raw.items():
        if not isinstance(righe, list) or not righe:
            raise DataError(f'{sym}: nessun record')
        m = {}
        prec = None
        for r in righe:
            if not isinstance(r, dict):
                raise DataError(f'{sym}: record non oggetto')
            try:
                day = int(r['day'])
            except (KeyError, TypeError, ValueError) as e:
                raise DataError(f'{sym}: campo day assente/invalido') from e
            if day % MS_GIORNO != 0:
                raise DataError(f'{sym}: day non allineato alla mezzanotte UTC: {day}')
            if prec is not None and day <= prec:
                raise DataError(f'{sym}: day fuori ordine o duplicato: {day} dopo {prec}')
            prec = day
            try:
                riga = {'day': day,
                        'sum_rate': _num(r['sum_rate'], f'{sym}.{day}.sum_rate'),
                        'n_epochs': int(r['n_epochs']),
                        'mean_rate': _num(r['mean_rate'], f'{sym}.{day}.mean_rate')}
            except (KeyError, TypeError, ValueError) as e:
                raise DataError(f'{sym} {day}: campi funding assenti/invalidi') from e
            if riga['n_epochs'] < 1:
                raise DataError(f'{sym} {day}: n_epochs < 1')
            m[day] = riga
        daily[sym] = m
    giorni = sorted({d for m in daily.values() for d in m})
    if not giorni:
        raise DataError('nessun giorno nel funding')
    for a, b in zip(giorni, giorni[1:]):
        if b - a != MS_GIORNO:
            raise DataError(f'giorni non consecutivi: {a} -> {b}')
    return daily, giorni


def _max_epoche(daily, giorno):
    return max((m[giorno]['n_epochs'] for m in daily.values() if giorno in m), default=0)


def split_finestre(daily, giorni):
    """Finestre congelate: 95 giorni pieni 28/07..30/10; 57 TRAIN + 38 OOS.

    Gli estremi della serie (27/07 e 31/10) devono essere PARZIALI (max n_epochs del
    giorno < max del vicino); altrimenti la struttura dei dati non e' quella della spec
    e si esce fail-closed.
    """
    if len(giorni) < 4:
        raise DataError('troppi pochi giorni')
    if (_max_epoche(daily, giorni[0]) >= _max_epoche(daily, giorni[1])
            or _max_epoche(daily, giorni[-1]) >= _max_epoche(daily, giorni[-2])):
        raise DataError('estremi non parziali: struttura giorni inattesa')
    pieni = giorni[1:-1]
    if len(pieni) != GIORNI_PIENI:
        raise DataError(f'giorni pieni {len(pieni)} != {GIORNI_PIENI}')
    return giorni, pieni, pieni[:GIORNI_TRAIN], pieni[GIORNI_TRAIN:]


def carica_candele(dati_dir, sym):
    """Bar spot+perp di un simbolo -> ({ts spot}, {ts perp}). Sola lettura."""
    out = {}
    for kind in ('spot', 'perp'):
        path = os.path.join(dati_dir, 'candles', kind, f'{sym}.json')
        if not os.path.exists(path):
            raise DataError(f'candela {kind} assente per {sym}: {path}')
        try:
            with open(path) as f:
                j = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise DataError(f'candela {kind} illeggibile per {sym}: {e}') from e
        try:
            ts = {int(c[0]) for c in j['candles']}
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise DataError(f'candela {kind} malformata per {sym}') from e
        out[kind] = ts
    return out


def carica_universo(dati_dir, daily):
    """Universo congelato: coppia spot (candele spot NON vuote) + >=90 bar spot E perp."""
    universi = {}
    esclusi = {'spot_vuote': 0, 'spot_lt90': 0, 'perp_lt90': 0, 'candele_assenti': 0}
    for sym in sorted(daily):
        try:
            bars = carica_candele(dati_dir, sym)
        except DataError:
            esclusi['candele_assenti'] += 1
            continue
        n_spot, n_perp = len(bars['spot']), len(bars['perp'])
        if n_spot == 0:
            esclusi['spot_vuote'] += 1
            continue
        if n_spot < MIN_BAR:
            esclusi['spot_lt90'] += 1
            continue
        if n_perp < MIN_BAR:
            esclusi['perp_lt90'] += 1
            continue
        universi[sym] = bars
    if not universi:
        raise DataError('universo vuoto dopo i filtri congelati')
    return universi, esclusi


def eseguibile(bars, giorno):
    """Esiste una bar spot E una perp che coprono l'inizio del giorno (ts <= g < ts+24h)?"""
    for kind in ('spot', 'perp'):
        ts = bars[kind]
        if not any(t <= giorno < t + MS_GIORNO for t in ts):
            return False
    return True


def sum_rate_di(daily, sym, giorno, default=0.0):
    riga = daily.get(sym, {}).get(giorno)
    return riga['sum_rate'] if riga is not None else default


def posizioni_per_giorno(universo, daily, giorni, cap=CAP_COPPIE):
    """Posizioni (regola congelata) per ogni giorno d in giorni[1:], usando segnali <= d-1.

    Ritorna {day: [syms in posizione]}, ordinate per FA(d-1) desc (tie instId).
    Pura: nessun accesso a candele, nessun RNG.
    """
    out = {}
    pos = set()
    for i in range(1, len(giorni)):
        d = giorni[i]
        d1 = giorni[i - 1]
        d2 = giorni[i - 2] if i >= 2 else None
        fa = {}
        for s in universo:
            riga = daily.get(s, {}).get(d1)
            if riga is not None:
                f = fa_giorno(riga)
                if f is not None:
                    fa[s] = f
        resta = []
        entra = []
        for s, f in fa.items():
            if s in pos:
                neg_ieri = d2 is not None and sum_rate_di(daily, s, d2) < 0.0
                neg_oggi = sum_rate_di(daily, s, d1) < 0.0
                if f >= SOGLIA_OUT and not (neg_ieri and neg_oggi):
                    resta.append(s)
            else:
                if f >= SOGLIA_IN:
                    entra.append(s)
        candidati = sorted(set(resta) | set(entra), key=lambda s: (-fa[s], s))
        scelti = candidati[:cap]
        pos = set(scelti)
        out[d] = scelti
    return out


def applica_eseguibilita(posizioni, universi, giorni):
    """Filtro eseguibilita' (bar spot+perp presenti): una coppia non eseguibile non entra
    (nessun costo) o esce forzata (nessun costo extra: RT gia' pagato all'ingresso)."""
    out = {}
    prec = set()
    casi = {'ingresso_bloccato': 0, 'uscita_forzata': 0}
    for d in giorni:
        effettivi = [s for s in posizioni[d] if eseguibile(universi[s], d)]
        for s in posizioni[d]:
            if s not in effettivi:
                if s in prec:
                    casi['uscita_forzata'] += 1
                else:
                    casi['ingresso_bloccato'] += 1
        out[d] = effettivi
        prec = set(effettivi)
    return out, casi


def pnl_per_giorno(posizioni, daily, giorni, nozionale, switch):
    """PnL giornaliero (EUR): funding incassato - costi di switch (RT anticipato all'ingresso).

    Ritorna (serie {day: pnl}, n_entrate, giorni_senza_funding_in_posizione, contributi).
    """
    serie = {}
    prec = set()
    n_entrate = 0
    senza_funding = 0
    contributi = {s: {'giorni': 0, 'funding': 0.0, 'costi': 0.0, 'entrate': 0} for s in
                  sorted({s for gg in giorni for s in posizioni[gg]})}
    for d in giorni:
        syms = posizioni[d]
        incasso = 0.0
        for s in syms:
            riga = daily.get(s, {}).get(d)
            if riga is None:
                senza_funding += 1
                continue
            v = riga['sum_rate'] * nozionale
            incasso += v
            contributi[s]['funding'] += v
            contributi[s]['giorni'] += 1
        entrate = [s for s in syms if s not in prec]
        costo = switch * nozionale * len(entrate)
        n_entrate += len(entrate)
        for s in entrate:
            contributi[s]['costi'] += switch * nozionale
            contributi[s]['entrate'] += 1
        serie[d] = incasso - costo
        prec = set(syms)
    for s, c in contributi.items():
        c['pnl_netto'] = c['funding'] - c['costi']
    return serie, n_entrate, senza_funding, contributi


def max_drawdown(serie_eur):
    """maxDD su PnL cumulato (EUR). Ritorna (maxdd_eur, maxdd_pct_su_capitale)."""
    cum = 0.0
    picco = 0.0
    dd = 0.0
    for p in serie_eur:
        cum += p
        picco = max(picco, cum)
        dd = max(dd, picco - cum)
    return dd, dd / CAPITALE


def metrica_finestra(pos_eff, serie, dettaglio, daily, giorni):
    """Tutte le metriche di una finestra (TRAIN o OOS), dalla serie CONTINUA.

    n_switch per finestra usa lo stato reale del giorno precedente al primo giorno della
    finestra (se fa parte della serie piena), cosi' il confine TRAIN/OOS non inventa
    costi di switch.
    """
    serie_eur = [serie[d] for d in giorni]
    serie_pct = [v / CAPITALE for v in serie_eur]
    pnl_tot = sum(serie_eur)
    t = st.t_stat(serie_pct)
    ci90 = (st.intervallo_media_iid(serie_pct, livello=0.90, seme=SEME_CI)
            if len(serie_pct) >= 2 else None)
    dd_eur, dd_pct = max_drawdown(serie_eur)
    giorni_pos = sum(1 for d in giorni if pos_eff[d])
    giorni_cap = sum(1 for d in giorni if len(pos_eff[d]) == CAP_COPPIE)
    prec = set(pos_eff[giorni[0] - MS_GIORNO]) if (giorni[0] - MS_GIORNO) in pos_eff else set()
    n_switch = 0
    senza = 0
    for d in giorni:
        syms = pos_eff[d]
        n_switch += sum(1 for s in syms if s not in prec)
        prec = set(syms)
        for s in syms:
            if daily.get(s, {}).get(d) is None:
                senza += 1
    contributi = aggregati_coppie(dettaglio, giorni)
    durate = [c['giorni'] for c in contributi.values() if c['giorni'] > 0]
    durata_media = sum(durate) / len(durate) if durate else 0.0
    return {
        'n_giorni': len(giorni),
        'giorni_inizio': giorni[0],
        'giorni_fine': giorni[-1],
        'n_giorni_con_posizioni': giorni_pos,
        'n_giorni_cap_pieno': giorni_cap,
        'n_switch': n_switch,
        'n_record_funding_mancanti': senza,
        'durata_media_posizione_giorni': durata_media,
        'pnl_totale_eur': pnl_tot,
        'rendimento_capitale': pnl_tot / CAPITALE,
        'baseline_earn_finestra': BASELINE_ANNUO * len(giorni) / 365.0,
        'media_giornaliera_eur': pnl_tot / len(giorni),
        'media_giornaliera_pct': pnl_tot / len(giorni) / CAPITALE,
        't_stat': t,
        'ci90_bootstrap_pct': list(ci90) if ci90 else None,
        'maxdd_eur': dd_eur,
        'maxdd_pct': dd_pct,
        'contributi_per_coppia': contributi,
        'serie_pnl_eur_per_giorno': {str(d): serie[d] for d in giorni},
    }


def gate_t1(m_oo):
    n, media, t = m_oo['n_giorni'], m_oo['media_giornaliera_eur'], m_oo['t_stat']
    motivo = []
    if n < T1_N_MIN:
        motivo.append(f'n {n} < {T1_N_MIN}')
    if media <= 0:
        motivo.append(f'media {media:.6f} <= 0')
    if t is None or t < T1_T_MIN:
        motivo.append(f't {t} < {T1_T_MIN}')
    return {'pass': not motivo, 'motivo': motivo or None,
            'n': n, 'media_eur': media, 't': t}


def gate_t2(m_oo_stress):
    media = m_oo_stress['media_giornaliera_eur']
    return {'pass': media > T2_MEAN_MIN, 'media_eur_stress': media,
            'switch_rt': SWITCH_STRESS}


def gate_t3(m_tr):
    media, t = m_tr['media_giornaliera_eur'], m_tr['t_stat']
    motivo = []
    if media <= 0:
        motivo.append(f'media {media:.6f} <= 0')
    if t is None or t < T3_T_MIN:
        motivo.append(f't {t} < {T3_T_MIN}')
    return {'pass': not motivo, 'motivo': motivo or None,
            'media_eur': media, 't': t}


def gate_t4(m_oo):
    rend, base = m_oo['rendimento_capitale'], m_oo['baseline_earn_finestra']
    return {'pass': rend > base, 'rendimento_capitale': rend, 'baseline': base}


def gate_dsr(m_oo):
    n = m_oo['n_giorni']
    serie_pct = [v / CAPITALE for v in m_oo['serie_pnl_eur_per_giorno'].values()]
    sr_annuo = st.sharpe(serie_pct, periodi_anno=365)
    if sr_annuo is None:
        return {'pass': False, 'motivo': 'sharpe non definito', 'dsr': None}
    var_tentativi = (1.0 + sr_annuo ** 2 / 2.0) / n   # varianza asintotica SR, dichiarata
    ing = st.sharpe_deflazionato(sr_annuo, n, N_TENTATIVI_DSR, var_tentativi)
    return {'pass': ing['dsr'] >= 0.95, 'dsr': ing['dsr'],
            'sharpe_annuo': sr_annuo, 'varianza_tentativi': var_tentativi,
            'ingredienti': ing}


def gate_concentrazione(m_oo):
    """Togliendo la coppia col contributo netto maggiore, la media OOS resta > 0."""
    contributi = m_oo['contributi_per_coppia']
    if not contributi:
        return {'pass': False, 'motivo': 'nessuna coppia'}
    top = max(contributi, key=lambda s: contributi[s]['pnl_netto'])
    top_pnl = contributi[top]['pnl_netto']
    serie_senza = [pnl - (top_pnl * 0.0 if False else 0.0) for pnl in
                   m_oo['serie_pnl_eur_per_giorno'].values()]
    # ricostruzione corretta: sottrarre il contributo GIORNALIERO della coppia top
    serie_senza = []
    for g, pnl in m_oo['serie_pnl_eur_per_giorno'].items():
        serie_senza.append(pnl - contributo_giornaliero(top, contributi, g))
    media = sum(serie_senza) / len(serie_senza) if serie_senza else None
    return {'pass': media is not None and media > 0, 'coppia_top': top,
            'pnl_netto_top_eur': top_pnl, 'media_senza_top_eur': media}


def calcola_serie(pos_eff, daily, giorni, nozionale, switch):
    """Serie di PnL CONTINUA (stato persistente tra giorni) con dettaglio per coppia.

    Ritorna (serie {day: pnl_eur}, dettaglio {sym: {day: {'funding','costo','netto',
    'presente'}}}, n_switch, n_giorni_senza_record_funding). Il costo di switch di una
    coppia e' addebitato nel giorno della sua ENTRATA reale (rispetto al giorno
    precedente della serie continua); la partizione TRAIN/OOS non azzera lo stato.
    """
    serie = {}
    dettaglio = {}
    prec = set()
    n_sw = 0
    senza = 0
    for d in giorni:
        syms = pos_eff[d]
        incasso = 0.0
        for s in syms:
            riga = daily.get(s, {}).get(d)
            v = riga['sum_rate'] * nozionale if riga is not None else 0.0
            if riga is None:
                senza += 1
            incasso += v
            e = dettaglio.setdefault(s, {}).setdefault(
                d, {'funding': 0.0, 'costo': 0.0, 'netto': 0.0})
            e['funding'] += v
            e['netto'] += v
            if riga is not None:
                e['presente'] = True
        entrate = [s for s in syms if s not in prec]
        costo_unit = switch * nozionale
        for s in entrate:
            e = dettaglio[s][d]
            e['costo'] += costo_unit
            e['netto'] -= costo_unit
        n_sw += len(entrate)
        serie[d] = incasso - costo_unit * len(entrate)
        prec = set(syms)
    return serie, dettaglio, n_sw, senza


def aggregati_coppie(dettaglio, giorni):
    """Contributi per coppia su una finestra di giorni (per il report e la concentrazione)."""
    out = {}
    for s, per_g in dettaglio.items():
        funding = costi = 0.0
        gg = ent = 0
        for d in giorni:
            e = per_g.get(d)
            if e is None:
                continue
            funding += e['funding']
            costi += e['costo']
            if e.get('presente'):
                gg += 1
            if e['costo'] != 0.0:
                ent += 1
        if gg == 0 and ent == 0:
            continue
        out[s] = {'giorni': gg, 'funding': funding, 'costi': costi,
                  'pnl_netto': funding - costi, 'entrate': ent}
    return out


def run(dati_dir):
    funding_path = os.path.join(dati_dir, 'funding_daily.json')
    daily, giorni_tutti = carica_funding(funding_path)
    giorni_tutti, pieni, giorni_train, giorni_oos = split_finestre(daily, giorni_tutti)
    universi, esclusi = carica_universo(dati_dir, daily)

    # posizioni della regola su TUTTI i giorni (segnali da giorni_tutti[0] incluso)
    posizioni = posizioni_per_giorno(list(universi), daily, giorni_tutti)
    # eseguibilita' e serie di PnL in UNA passata continua sui 95 giorni pieni:
    # lo stato non si azzera al confine TRAIN/OOS (il pnl e' una serie temporale)
    pos_eff, casi = applica_eseguibilita(posizioni, universi, pieni)
    serie_base, dettaglio_base, n_sw_base, _ = calcola_serie(
        pos_eff, daily, pieni, nozionale_per_coppia(), SWITCH_BASE)
    serie_stress, dettaglio_stress, n_sw_stress, _ = calcola_serie(
        pos_eff, daily, pieni, nozionale_per_coppia(), SWITCH_STRESS)

    m_train = metrica_finestra(pos_eff, serie_base, dettaglio_base, daily, giorni_train)
    m_oos = metrica_finestra(pos_eff, serie_base, dettaglio_base, daily, giorni_oos)
    m_oos_stress = metrica_finestra(pos_eff, serie_stress, dettaglio_stress, daily, giorni_oos)

    def concentrazione():
        contributi = m_oos['contributi_per_coppia']
        if not contributi:
            return {'pass': False, 'motivo': 'nessuna coppia'}
        top = max(contributi, key=lambda s: contributi[s]['pnl_netto'])
        serie_senza = []
        for d in giorni_oos:
            contrib = (dettaglio_base.get(top, {}).get(d) or {}).get('netto', 0.0)
            serie_senza.append(serie_base[d] - contrib)
        media = sum(serie_senza) / len(serie_senza)
        return {'pass': media > 0, 'coppia_top': top,
                'pnl_netto_top_eur': contributi[top]['pnl_netto'],
                'media_senza_top_eur': media}

    g1 = gate_t1(m_oos)
    g2 = gate_t2(m_oos_stress)
    g3 = gate_t3(m_train)
    g4 = gate_t4(m_oos)
    gd = gate_dsr(m_oos)
    gc = concentrazione()
    gates = {'T1': g1, 'T2': g2, 'T3': g3, 'T4': g4, 'DSR': gd, 'concentrazione': gc}
    per_gate = {k: bool(v['pass']) for k, v in gates.items()}
    esito = 'PASS' if all(per_gate.values()) else 'FAIL'

    coppie_oos = sorted(m_oos['contributi_per_coppia'].items(),
                        key=lambda kv: (-kv[1]['pnl_netto'], kv[0]))

    return {
        'spec': {
            'capitale_eur': CAPITALE, 'cap_coppie': CAP_COPPIE,
            'nozionale_per_coppia_eur': nozionale_per_coppia(),
            'capitale_vincolato_per_coppia_eur': capitale_vincolato_per_coppia(),
            'capitale_vincolato_totale_eur': capitale_vincolato_totale(),
            'soglia_ingresso_fa_pct': SOGLIA_IN, 'soglia_uscita_fa_pct': SOGLIA_OUT,
            'giorni_negativi_per_uscita': GIORNI_NEG_ESC,
            'switch_rt_base': SWITCH_BASE, 'switch_rt_stress': SWITCH_STRESS,
            'min_bar_storia': MIN_BAR, 't1_n_min': T1_N_MIN, 't1_t_min': T1_T_MIN,
            't2_mean_min': T2_MEAN_MIN, 't3_t_min': T3_T_MIN,
            'baseline_annuo': BASELINE_ANNUO, 'n_tentativi_dsr': N_TENTATIVI_DSR,
            'seme_ci_bootstrap': SEME_CI, 'giorni_train': GIORNI_TRAIN,
            'giorni_oos': GIORNI_OOS,
        },
        'input': {
            'funding_daily_sha256': hashlib.sha256(
                open(funding_path, 'rb').read()).hexdigest(),
            'codice_engine_sha256': hashlib.sha256(
                open(os.path.abspath(__file__), 'rb').read()).hexdigest(),
            'n_simboli_funding': len(daily),
        },
        'giorni': {
            'primo_ms': giorni_tutti[0], 'ultimo_ms': giorni_tutti[-1],
            'primo_parziale': True, 'ultimo_parziale': True,
            'n_pieni': len(pieni),
            'train': {'inizio_ms': giorni_train[0], 'fine_ms': giorni_train[-1],
                      'n': len(giorni_train)},
            'oos': {'inizio_ms': giorni_oos[0], 'fine_ms': giorni_oos[-1],
                    'n': len(giorni_oos)},
        },
        'universo': {'n_funding': len(daily), 'esclusi': esclusi,
                     'n_universo': len(universi), 'lista': sorted(universi)},
        'casi_limite': {'totale_95gg': casi, 'n_switch_base': n_sw_base,
                        'n_switch_stress': n_sw_stress},
        'per_finestra': {'TRAIN': m_train, 'OOS': m_oos, 'OOS_STRESS': m_oos_stress},
        'coppie_oos': [{**({'instId': s}), **c} for s, c in coppie_oos],
        'gates': gates,
        'verdetto': {'esito': esito, 'per_gate': per_gate},
        'dichiarazioni': [
            'PnL = funding netto - costi switch; NESSUN mark-to-market della basis '
            '(ipotesi congelata: "incassa il funding netto dopo fee e ribilanciamenti").',
            'Switch RT intero addebitato all INGRESSO della coppia (conservativo: '
            'anticipa il costo di chiusura; rientri pagano di nuovo). Uscita: costo zero.',
            'Candele 1D usate solo per universo (>=90 bar) ed eseguibilita (bar che copre '
            'linizio del giorno); bar del preflight allineate alle 16:00 UTC (verificato).',
            '27/07 (n_epochs=1, cut OKX 16:00Z) usato SOLO come segnale del 28/07: FA '
            'sottostimato ~1/3 quel giorno (formula letterale della spec, n_epochs(t)).',
            '31/10 (parziale, fuori finestra) non usato ne come segnale ne come misura.',
            'FA assente (nessun record funding a d-1) -> la coppia NON resta in posizione.',
            'Record funding assente per una coppia in posizione: contributo 0, conteggiato '
            'in n_record_funding_mancanti.',
            'DSR: sharpe_deflazionato (Bailey & Lopez de Prado) con n_tentativi=2 e '
            'varianza tentativi = (1 + SR^2/2)/n (varianza asintotica dello Sharpe, '
            'nessun trial aggiuntivo eseguito: soglie congelate).',
            'CI90: bootstrap i.i.d. su media giornaliera, seme fisso 20260101 '
            '(convenzione money.statistica).',
            'Selezione top-5 per FA(d-1) desc, tie-break instId (deterministico).',
        ],
    }


def render_txt(res):
    L = []
    A = L.append
    sp = res['spec']
    A('E15 — carry funding a soglia su universo perp OKX (smoke da dati CONGELATI NUV-009)')
    A(f"regola: ingresso FA>={sp['soglia_ingresso_fa_pct']}% | uscita FA<{sp['soglia_uscita_fa_pct']}% "
      f"o funding negativo x2gg | cap {sp['cap_coppie']} coppie")
    A(f"capitale {sp['capitale_eur']:.0f} EUR | nozionale/coppia {sp['nozionale_per_coppia_eur']:.0f} EUR "
      f"| vincolato/coppia {sp['capitale_vincolato_per_coppia_eur']:.0f} EUR | "
      f"switch {sp['switch_rt_base']*10000:.0f}bp RT (stress {sp['switch_rt_stress']*10000:.0f}bp)")
    g = res['giorni']
    A(f"giorni pieni: {g['n_pieni']} | TRAIN {g['train']['n']} | OOS {g['oos']['n']} "
      f"(primo {g['primo_ms']} e ultimo {g['ultimo_ms']} parziali)")
    u = res['universo']
    A(f"universo: {u['n_funding']} perp funding -> {u['n_universo']} con coppia spot e >=90 bar "
      f"(esclusi: {u['esclusi']})")
    for nome in ('TRAIN', 'OOS', 'OOS_STRESS'):
        m = res['per_finestra'][nome]
        t = 'None' if m['t_stat'] is None else f"{m['t_stat']:+.3f}"
        ci = m['ci90_bootstrap_pct']
        cis = f"CI90 [{ci[0]*100:+.4f}%, {ci[1]*100:+.4f}%]" if ci else 'CI90 n/a'
        A(f"[{nome}] n={m['n_giorni']}gg (pos {m['n_giorni_con_posizioni']}, cap pieno "
          f"{m['n_giorni_cap_pieno']}) | pnl tot {m['pnl_totale_eur']:+.2f} EUR | "
          f"media {m['media_giornaliera_eur']:+.4f} EUR/gg ({m['media_giornaliera_pct']*100:+.4f}%) "
          f"| t={t} | {cis} | maxDD {m['maxdd_eur']:.2f} EUR ({m['maxdd_pct']*100:.2f}%) | "
          f"switch {m['n_switch']} | rendim. {m['rendimento_capitale']*100:+.3f}% "
          f"(base Earn {m['baseline_earn_finestra']*100:.3f}%)")
    A('--- GATE ---')
    for nome, x in res['gates'].items():
        extra = ''
        if nome == 'T2':
            extra = f" media_stress={x['media_eur_stress']:+.5f} EUR/gg"
        if nome == 'T4':
            extra = f" rend={x['rendimento_capitale']*100:+.4f}% base={x['baseline']*100:.4f}%"
        if nome == 'DSR':
            extra = f" dsr={x['dsr']:.4f} SR_ann={x.get('sharpe_annuo', float('nan')):.2f}"
        if nome == 'concentrazione':
            extra = (f" top={x.get('coppia_top')} "
                     f"pnl_top={x.get('pnl_netto_top_eur', float('nan')):+.2f} EUR "
                     f"media_senza={x.get('media_senza_top_eur', float('nan')):+.5f} EUR/gg")
        motivo = f" [{x['motivo']}]" if x.get('motivo') else ''
        A(f"  {nome}: pass={x['pass']}{extra}{motivo}")
    A(f"VERDETTO: {res['verdetto']['esito']} {res['verdetto']['per_gate']}")
    A('--- top coppie OOS per pnl netto ---')
    for c in res['coppie_oos'][:10]:
        A(f"  {c['instId']:24s} giorni={c['giorni']:3d} funding={c['funding']:+.4f} "
          f"costi={c['costi']:.4f} pnl={c['pnl_netto']:+.4f} EUR")
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dati-dir', required=True)
    ap.add_argument('--out-prove', required=True)
    a = ap.parse_args(argv)
    if not os.path.isdir(a.dati_dir):
        print(f'ERROE: dati-dir non esistente: {a.dati_dir}', file=sys.stderr)
        return 2
    try:
        res = run(a.dati_dir)
    except DataError as e:
        print(f'FAIL-CLOSED: {e}', file=sys.stderr)
        return 2
    os.makedirs(a.out_prove, exist_ok=True)
    out_json = os.path.join(a.out_prove, 'e15_carry_soglia.json')
    out_txt = os.path.join(a.out_prove, 'e15_carry_soglia.txt')
    with open(out_json, 'w') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    txt = render_txt(res)
    with open(out_txt, 'w') as f:
        f.write(txt)
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
