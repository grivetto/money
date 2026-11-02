# DOSSIER PER REVISIONE ESTERNA — Il cancello di promozione di Denaro

Data: 2026-11-02 · Autore del dossier: Hermes (Artù, ingegnere capo) · Destinatario: Manus AI (parere esterno)

Questo dossier contiene il **codice reale** del cancello di promozione delle strategie
del progetto Denaro (`~/money`, repo `grivetto/money`) e il ragionamento che lo sostiene,
compresi i punti in cui sospettiamo che sia troppo restrittivo. Le omissioni sono
dichiarate esplicitamente: i file integrali sono `src/money/cancello.py` (1028 righe)
e `src/money/statistica.py` (470 righe); qui è incluso tutto il codice **decisionale**,
mentre docstring lunghi e formattazione dei "motivi" sono riassunti.

---

## 1. I fatti, prima del codice

- 0 strategie promosse su ~19 esperimenti pre-registrati (E1–E19, tutti con spec
  congelata PRIMA dei numeri, dati congelati, test anti-look-ahead, misura ripetuta
  bit-a-bit su due macchine).
- Loop di ricerca automatici S1/S3 (griglie di 512 e 1760 tentativi/giorno, ~322–1144
  valutabili): **0 candidati** sopra soglia in mesi di esecuzione.
- Capitale reale: ~1.100 €. Tetto di rischio dichiarato: 500 €. Una strategia sotto
  10 €/anno attesi non giustifica un sistema acceso H24 (criterio 7).
- Fee reali misurate: OKX spot 8 bp maker / 10 bp taker per lato; perp 2/5 bp;
  giro "misto" tipico ~0,18 %.
- Il progetto precedente (49.162 righe, zero profitto) promuoveva strategie senza
  criterio statistico ("il backtest sembrava buono"). Questo cancello è nato come
  antidoto a quello.

La domanda che vi poniamo non è "il cancello è troppo severo?" in astratto, ma:
**dove il costo dei falsi negativi supera il costo dei falsi positivi che previene,
su questo capitale e con queste fee?**

---

## 2. Architettura

- Tre verdetti: `promosso` (tutti i criteri), `archiviato` (almeno un criterio fallisce
  con dati sufficienti), `insufficiente` (i dati non bastano per dire né sì né no:
  n < 30, serie malformate, deviazione standard nulla).
- AND di 8 criteri, tutti valutati sempre (anche se uno fallisce), ogni motivo contiene
  il numero che lo sostiene ("expectancy +0,31 % < 3x pedaggio 0,55 % = 1,65 %").
- Riproducibilità: seme bootstrap fisso e dichiarato; due run sugli stessi dati danno
  lo stesso verdetto.
- `bool(verdetto)` è True solo per "promosso": il codice di produzione si scrive
  `if not giudica(esito): return` — non esiste scorciatoia.

## 3. Le soglie (codice reale, cancello.py righe 114–160)

```python
MIN_OPERAZIONI: int = 30          # sotto: verdetto "insufficiente", non "archiviato"
MIN_N_EFFETTIVO: float = 30.0     # osservazioni indipendenti stimate (autocorr.-corrette)
LIVELLO_CONFIDENZA: float = 0.90  # IC bootstrap sull'expectancy
RICAMPIONAMENTI: int = 10_000
SEME_BOOTSTRAP: int = 20260101    # fisso e dichiarato: riproducibilità
T_STAT_MINIMO: float = 1.65       # t una coda, 5% (z per campioni grandi)
PROFIT_FACTOR_MINIMO: float = 1.20
MAX_DRAWDOWN: float = 0.25        # sul capitale di riferimento
MARGINE_PEDAGGIO: float = 3.0     # expectancy netta >= 3x costo giro completo
CAPITALE_RIFERIMENTO_DEFAULT: float = 1_000.0
SOGLIA_EUR_ANNO_DEFAULT: float = 10.0
GIORNI_ANNO: float = 365.0        # crypto H24, non 252
OPERAZIONI_GIORNO_SOSPETTE: float = 50.0  # oltre: l'estrapolazione annua è avvertita
```

## 4. Gli 8 criteri (codice reale, corpi delle funzioni c_*)

```python
def c_numerosita(esito, s, opt):
    n = len(esito.ritorni_netti)
    ok = n >= opt["min_operazioni"] and s.get("n_effettivo") >= opt["min_n_effettivo"]
    # n_effettivo = n / (1 + 2*sum(rho_k)) troncato alla prima autocorr. non positiva
    return ok, motivo_con_numeri, {"n": n, "n_effettivo": s.get("n_effettivo")}

def c_expectancy(esito, s, opt):
    # IC bootstrap al 90% sulla MEDIA dei ritorni netti: estremo inferiore > 0
    # bootstrap non parametrico (niente assunzione di normalità: code grasse)
    # se autocorrelazione(1) rilevante (> 2/sqrt(n)): richiesto ANCHE l'IC a blocchi
    inf, sup = s["ic_bootstrap"]
    ok = inf > 0.0
    if s.get("dipendenza_rilevante"):
        inf_b, sup_b = s["ic_block"]  # bootstrap a blocchi circolari
        ok = ok and inf_b > 0.0
    return ok, motivo_con_numeri, {"ic_inf": inf, "ic_sup": sup}

def c_tstat(esito, s, opt):
    t = s["t_stat"]; mn = opt["t_minimo"]
    if s.get("dipendenza_rilevante") and s.get("t_hac") is not None:
        t_eff = min(t, s["t_hac"])   # t naive vs t Newey-West: vale il conservativo
        ok = t_eff > mn
    else:
        ok = t > mn
    return ok, motivo_con_numeri, {"t_eff": t_eff}

def c_profit_factor(esito, s, opt):
    pf = s["profit_factor"]  # somma positivi / |somma negativi|, inf se nessun negativo
    return pf > opt["pf_minimo"], motivo_con_numeri, {"profit_factor": pf}

def c_drawdown(esito, s, opt):
    dd = esito.max_drawdown  # frazione del capitale di riferimento
    return 0.0 <= dd <= opt["max_drawdown"], motivo_con_numeri, {"max_drawdown": dd}

def c_pedaggio(esito, s, opt):
    # il criterio che il progetto precedente non aveva: l'edge vs il costo di esistere
    exp = s["expectancy"]                 # GIÀ netta di fee e slippage
    ped = esito.pedaggio_per_operazione   # costo giro completo, tariffa dichiarata
    k = opt["margine_pedaggio"]
    return exp >= ped * k, motivo_con_numeri, {"pedaggio": ped, "soglia_pedaggio": ped * k}

def c_rilevanza(esito, s, opt):
    # guadagno annuo atteso = expectancy * capitale * esposizione_media * op/anno
    # estrapolazione lineare composta: dichiarata come LIMITE SUPERIORE, non previsione
    g = opt["guadagno"]
    return g["eur_anno"] >= opt["soglia_eur"], motivo_con_numeri, {"eur_anno": g["eur_anno"]}

def c_blocchi(esito, s, opt):
    # serie partizionata in n_blocchi=3 blocchi CONTIGUI quasi uguali
    # tolto il blocco migliore, l'expectancy netta media dei restanti deve restare > 0
    # (opzionale: confini espliciti "bricole" per partizioni bull/range/bear)
    blocchi, exp_netta, migliore, senza = _blocchi_netti(esito, opt["n_blocchi"], opt["bricole"])
    return senza is not None and senza > 0.0, scomposizione.motivo, {...}
```

Il flusso `giudica()` (cancello.py righe 775–923), in sintesi:

1. Dati degeneri (lunghezza incoerente, NaN, dev_std nulla, max_drawdown negativo) →
   `insufficiente` con motivo. Mai un'eccezione.
2. n < 30 (o n_effettivo < 30) → `insufficiente`: "l'errore standard della media è
   X contro un'expectancy di Y: promuovere sarebbe un azzardo, archiviare sarebbe
   buttare via la strategia".
3. Tutti gli 8 criteri in AND; anche se uno fallisce gli altri sono comunque valutati,
   così si sa ESATTAMENTE cosa cambierebbe abbassando una soglia.
4. Se nessun motivo → `promosso`.

Dipendenze temporali (righe 837–858 di giudica, revisione esterna 06/10 già integrata):

```python
_ac1 = statistica.autocorrelazione(esito.ritorni_netti, 1)
dipendenza = abs(_ac1) > 2.0 / math.sqrt(n)      # rilevanza dell'autocorrelazione
blocco = max(2, int(round(n ** (1.0 / 3.0))))    # lunghezza blocco bootstrap
t_hac, se_hac = statistica.t_stat_newey_west(esito.ritorni_netti)
s["n_effettivo"] = statistica.n_effettivo(esito.ritorni_netti)
if dipendenza:
    s["ic_block"] = statistica.intervallo_media_blocchi(esito.ritorni_netti, blocco, ...)
```

## 5. Le correzioni contro il selection bias (statistica.py, codice reale)

```python
def sharpe_atteso_massimo(n_tentativi, varianza_sharpe_tentativi):
    # Bailey & Lopez de Prado: Sharpe atteso del MIGLIORE di N tentativi quando il
    # vero Sharpe è zero
    # = sqrt(V) * [(1-g) Z^-1(1-1/N) + g Z^-1(1-1/(N e))], g = costante di Eulero
    ...

def sharpe_deflazionato(sharpe_osservato, n_osservazioni, n_tentativi,
                        varianza_sharpe_tentativi, skew=0.0, kurtosis=3.0):
    # DSR: probabilità che lo Sharpe osservato NON sia il massimo di N prove a vuoto
    sr0 = sharpe_atteso_massimo(n_tentativi, varianza_sharpe_tentativi)
    z = (sr - sr0) * sqrt(n_osservazioni - 1) / sqrt(1 - skew*sr + (kurtosis-1)/4*sr**2)
    return {"dsr": norm_cdf(z), "sharpe_osservato": sr, "sharpe_atteso_massimo": sr0, ...}

def pbo_cscv(serie_config, blocchi=10, max_combinazioni=5000, seme=20260101):
    # Probability of Backtest Overfitting via CSCV: partizione del tempo in blocchi pari,
    # tutte le combinazioni metà/metà, config migliore scelta IN CAMPIONE, posizione
    # misurata FUORI CAMPIONE. pbo ~ 0.5 = la selezione è una moneta.
    ...
```

Nei loop S1/S3 la soglia di promozione usa DSR >= 0.95 con il benchmark dichiarato
E[max SR] ~ 0.370 per operazione (322–1144 tentativi valutabili).

## 6. Analisi onesta: dove il cancello è severo, dove è lasco, dove è incompleto

### 6.1 Punti di forza (non negoziabili)
- Asimmetria voluta: sul capitale attuale un falso positivo brucia capitale fino al
  tetto (500 €); un falso negativo costa al massimo l'edge mancato, che per costruzione
  (criterio 7) vale < 10 €/anno. L'asimmetria è GIUSTA a questo capitale.
- Ogni verdetto è riproducibile e discute i numeri, non le impressioni.

### 6.2 Punti dove il cancello è probabilmente TROPPO restrittivo

(a) **Criterio 6, margine 3x fisso.** Con giro misto 0,18 % serve expectancy
    >= 0,54 %/trade. Per strategie lente (mensili) è quasi gratis (le top delle
    scansioni stanno a 6–12 %/trade); per strategie sub-giornaliere è spesso
    irraggiungibile anche con edge reale, perché lo slippage vero (non quello
    assunto) è una variabile con errore che cresce col turnover. Un margine fisso
    3x non tiene conto dell'incertezza di stima né dello slippage. Alternativa
    candidata: soglia che cresce con SE(expectancy), es. exp >= k·ped + 2·SE(exp).

(b) **Criterio 8 senza margine.** "Senza il blocco migliore resta > 0" su 3 blocchi:
    con n=30–40 (cioè 10–13 op/blocco) l'errore standard di un blocco è enorme; un
    edge vero piccolo ha probabilità alta che il blocco migliore porti tutto e il
    resto sia ≈ 0 → archiviato. Candidati alternativi: soglia su k su m blocchi
    positivi, blocchi sovrapposti, o confronto con la distribuzione nulla.

(c) **Ridondanza statistica.** Criterio 2 (IC90 bootstrap > 0) e criterio 3
    (t > 1,65) sono quasi la stessa ipotesi su distribuzioni simmetriche: la
    congiunzione non aggiunge protezione ma raddoppia il costo sui casi limite.
    Nei loop, il DSR 0,95 si somma a IC90 + t + PF + DD dopo che la selezione
    è già stata pagata dalla validazione out-of-sample: tripla protezione contro
    lo stesso rischio (selection bias), con potenza decimata. Con N=322 e
    varianza Sharpe 0,0048 (documentata in E8) l'E[max SR] è ~0,20/operazione:
    un edge reale SR=0,3 con n=100 ha DSR ben sotto 0,95 quasi sempre.

(d) **n_min = 30 senza processo di accumulo.** Per strategie lente (1 op/mese)
    servono 2,5+ anni; il verdetto dice "raccogli altri dati" ma nessun processo
    accumula automaticamente operazioni verso la soglia. Le strategie lente
    muoiono di attesa, non di verdetto. Alternativa candidata: soglia sull'errore
    standard relativo (SE/expectancy < k) invece che n fisso.

### 6.3 Punti dove il cancello è invece LASCO o incompleto

(e) **Nessun confronto col benchmark passivo.** Una strategia long-only che rende
    come buy&hold passa tutti gli 8 criteri ma non aggiunge valore. In E11 il
    confronto è stato aggiunto ad hoc (T4: maxDD strategia <= maxDD buy&hold);
    manca nel cancello un criterio di rendimento in eccesso.

(f) **t > 1,65 con n grande è debole.** Con n=500, t=1,65 ⇔ Sharpe per trade
    ~0,074: il criterio 3 da solo non è una protezione per campioni lunghi
    (compensato dal DSR nei loop, non nelle spec singole).

### 6.4 Le domande precise per la revisione

1. Criteri 2 e 3: la congiunzione IC90-bootstrap AND t>1,65 è intenzionale o
   ridondante? In quali distribuzioni (asimmetria, code grasse) i due divergono,
   e quale dei due dovrebbe prevalere lì?
2. Criterio 6: margine fisso 3x vs margine funzione dell'incertezza di stima
   (es. exp >= 3·ped + 2·SE) o dello slippage al 95° pct: quale è più adatto a
   strategie con turnover > 1/giorno?
3. Criterio 8: con n=30–40, "senza il migliore > 0" su 3 blocchi è quasi un
   criterio di impossibilità. Quale formulazione mantiene la protezione contro
   la dipendenza da un regime ma con potenza accettabile?
4. DSR 0,95 in AND con IC90+t+PF+DD, quando la selezione è già pagata dalla
   validazione OOS: qual è la combinazione minima che controlla il selection
   bias senza uccidere la potenza? (Dati per la calibrazione: N tentativi
   322–1144, varianza Sharpe tentativi 0,0048 misurata, n per candidato 30–100.)
5. La soglia "insufficiente" (n_min=30, n_eff 30) ha senso come soglia fissa, o è
   meglio una soglia sull'errore standard relativo dell'expectancy?
6. Dove inserire il confronto col benchmark passivo: criterio 9 nel cancello o
   confronto descrittivo per-spec?
7. Nel complesso: date fee misurate (0,18 %/giro), capitale 1.100 €, tetto 500 €,
   soglia rilevanza 10 €/anno — c'è un modo formale di scegliere le soglie in base
   al rapporto costo-falso-positivo / costo-falso-negativo, invece di soglie
   assolute scelte a sensazione?

---

File integrali: `src/money/cancello.py`, `src/money/statistica.py`, `src/money/costi.py`
(tariffe e movimento minimo) nel repo `grivetto/money`, commit ff95bcf3.
