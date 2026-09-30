# P11 — Volatility breakout ATR (famiglia nuova, coda parallela — direttiva "x5" 30/09)
STATO: PRESA_DA A0-PC (modulo+test, brief dispacciato) + hermes (misura) — 2026-09-30
REPO: money @ commit `e110e545` (al momento della materializzazione della spec)
DATI: USDT-lungo (10 majors; 2020-10-01 -> 2026-09-25; confine addestramento 2024-06-01)

## Ipotesi
Un breakout NORMALIZZATO PER VOLATILITA' (la chiusura si muove oltre k unita' di ATR
rispetto al giorno prima) riconosce l'INIZIO di un movimento con una sola regola: lo
stesso salto vale di piu' in un regime quieto e conta meno in un regime agitato.
(Voce "volatility breakout ATR" della coda DSH del 27/09, rimasta non misurata.)

## Meccanica
- Ingresso: long quando `chiusura[i]/chiusura[i-1] - 1 > k * ATR%(i-1)`, con
  ATR%(j) = media semplice dei true range delle ultime 14 barre di indici [j-13 .. j]
  (ciascun TR richiede la chiusura precedente; solo dati <= j); None se storia insufficiente.
  Confronto STRETTO (>): alla parita' non si entra.
- Uscita: alla rottura del minimo delle ultime M barre (stessa forma del canale P1/P2):
  si vende all'apertura di j quando `chiusura[j-1] < min(minimi[j-1-M .. j-2])`;
  a fine serie la posizione aperta si chiude all'ultima apertura disponibile
  (motivo "fine serie"), come nel motore Donchian.
- Esecuzione: all'apertura della barra successiva al segnale (anti-look-ahead).
- Allocazione/portafoglio: modello `backtest_portafoglio` (0.25 x equity per operazione,
  cassa vincolante, niente leva) — come P6.

## Griglia (dichiarata, 6 varianti) — PRIMA dei numeri
`{k: 1.0, 1.5, 2.0}` x `{M: 10, 20}` = **6 configurazioni**.
Selezione: SOLO addestramento (n >= 30, max expectancy netta); verifica: una sola.

## Metriche e criterio di successo
- Primaria: DD di portafoglio mark-to-market (motore `portafoglio.py`).
- Successo: DDport <= 25% E expectancy >= 3x pedaggio (stessa regola di P2/P6).
- Secondarie: EUR/anno, eseguiti/saltati, t-stat (Newey-West accanto), scheda economica
  E1 (cost-to-edge) accanto al verdetto. Artefatti: `prove/P11_vol_breakout.{txt,json}`.

## Nota dichiarata
Regola standard: se fallisce, si archivia per costruzione. La coda successiva e' P12
(4h + filtro di regime, coda DSH) oppure il filone funding quando i dati maturano.
