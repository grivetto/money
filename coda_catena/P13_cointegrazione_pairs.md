# P13 — Cointegrazione: pairs/basket sui major (lane nuova)
STATO: PRESA_DA hermes 2026-10-01
DATI: USDT-lungo (`dati.py`, 2020-10-01 → oggi; confine addestramento 2024-06-01) per il test
statistico e la verifica. La conferma finale pre-promozione si rifà sui simboli TRADABILI
(X-Perp EEA + spot), dove però la storia è corta (~3 mesi: dichiarato, attenzione).

## Ipotesi
Coppie di major crypto possono avere relazioni di equilibrio **instabili ma sfruttabili**:
quando lo spread si allontana dall'equilibrio, tende a rientrare. Razionale economico:
(a) panieri che condividono driver comuni (beta a BTC, cicli di settore L1/smart-contract);
(b) i disallineamenti nascono da flussi e attenzione asimmetrici nel breve, non da
fondamentali separati — quindi rientrano. Contro-razionale dichiarato: in crypto la
cointegrazione su finestre corte è notoriamente fragile e può sparire fuori campione;
per questo lo screening è severo e il kill rapido è un esito previsto e accettato.

## Screening (fase 1 — dichiarata, niente ottimizzazione)
- Coppie: le 10 major dell'archivio X-Perp (BTC, ETH, SOL, DOGE, XRP, ADA, AVAX, LINK, LTC,
  DOT) → C(10,2) = **45 coppie**. Si testano TUTTE; soglia corretta per 45 test.
- Test EG (Engle-Granger due passi) su ADDESTRAMENTO [2020-10-01, 2024-06-01):
  OLS log(P_a) = alfa + beta·log(P_b); ADF sui residui; soglia dichiarata **|t_rho| ≥ 3,8**
  (conservativa per 45 test); half-life = −ln2/ln(1+rho) in **[3, 30] giorni**; stabilità di
  beta tra le due sotto-finestre dell'addestramento: |Δbeta|/beta ≤ 30%.
- Selezione: si ordinano le coppie che passano per |t_rho| decrescente; **massimo 3 coppie**
  (cap dichiarato per il capitale). Se nessuna passa → lane **archiviata subito** (kill rapido).

## Regole operative (fase 2 — congelate)
- z(t) = (spread(t) − media_60g(t)) / sd_60g(t), tutto calcolato su osservazioni ≤ t.
- Ingresso: |z| ≥ 2 allo close t → esecuzione all'apertura t+1. z>2 = short spread
  (short gamba A, long gamba B); z<−2 = long spread. Una posizione per coppia.
- Uscita: |z| ≤ 0,5 oppure stop |z| ≥ 4 oppure fine serie.
- Capitale: 0,25× equity per coppia (due gambe perp, margine isolato 1×; NIENTE leva).
- **Griglia: UNICA** (2 / 0,5 / 4 / 60g = valori dichiarati, non ottimizzati). Ogni variante
  ulteriore = nuova voce di registro.

## Costi e funding
- Perp, due gambe: 0,05%×2 taker per gamba → 0,10% per giro per gamba; coppia = 0,20% per
  giro completo + slippage 0,05% per gamba per giro → **ciclo dichiarato ≈ 0,30%**.
- FUNDING delle due gambe incluso nel P&L (short riceve su funding positivo, long paga):
  sul netto incide il DIFFERENZIALE di funding tra le gambe; misurato e riportato.
- Pre-promozione: riconti sulle tariffe reali delle gambe effettive.

## Verifica OOS e criteri (cancello)
- Verifica [2024-06-01, oggi], **una volta sola**, configurazione congelata dallo screening.
- Successo: **DDport ≤ 25% E expectancy netta (campione eseguito) ≥ 3× pedaggio**.
- Secondarie riportate sempre: t-stat, n (se < 30 → "insufficiente", mai "promossa"),
  PF > 1,20, criterio 8 (indipendenza dai blocchi), risultati per le due metà della verifica.
- Se il segno dell'expectancy cambia tra le due metà → archiviata.

## Rottura della relazione (rischio principe)
- Lo stop |z| ≥ 4 è un limitatore grezzo; si misura la frequenza di ROTTURE (z sfondato e non
  rientrato entro 30 giorni): **> 20% degli episodi → coppia esclusa** a prescindere dal P&L.
- Diagnostica obbligatoria: half-life stimata nella verifica vs addestramento; se esplode,
  l'edge è morto (archiviata).

## Anti-bias
- Anti-lookahead: statistiche solo su osservazioni ≤ t; esecuzione t+1; test dedicati nei
  `tests/ricerca/` PRIMA dei numeri.
- Multiple testing: 45 test → soglia corretta dichiarata; selezione SOLO su addestramento.
- Survivorship: universo = major listate oggi (dichiarato; delisting non rappresentato).
- Niente P&L di funding nascosto: il funding differenziale è parte della misura.
- Stabilità di beta obbligatoria in addestramento: nessuna coppia "bella in una sola finestra".

## Riferimenti
`docs/18_programma_ricerca_quant.md` (protocollo) · P12 (le gambe perp pagano/ricevono
funding) · `src/money/dati.py` (USDT-lungo) · cancello (`src/money/cancello.py`).
