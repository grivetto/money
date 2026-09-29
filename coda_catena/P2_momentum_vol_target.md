# P2 — Momentum assoluto con position sizing a volatilita' (vol targeting)
STATO: PRESA_DA dsh (2026-09-29)
DATI: USDT-lungo (2019-01-01 -> oggi; confine 2024-06-01)

## Ipotesi
Il nodo L (momentum assoluto 60g) ha +2,61% netto e DD 57%: la scommessa e' che il DD veniva
dai tratti ad alta volatilita' in cui la posizione era sempre piena. Regola: dentro/fuori
come L (long se ritorno 60g > 0), ma l'esposizione di OGNI operazione e'
`min(1, vol_target / vol_realizzata_20g)`, vol_target = 60% annualizzata. Nei backtest il
ritorno per operazione si scala per il fattore di esposizione.

## Meccanica
- Segnale: ritorno 60g > 0 alla chiusura di i -> lungo all'apertura di i+1 (come L).
- Sizing per operazione: f = min(1.0, 0.60 / (sigma20 * sqrt(365))), sigma20 = dev std dei
  rendimenti giornalieri FINO a i (solo passato).
- Ritorno lordo dell'operazione = f * (prezzo_uscita/prezzo_ingresso - 1). Il pedaggio si
  paga sul nozionale IMPEGNATO (f * posizione): attenzione a scalare anche quello.
- Una posizione alla volta per simbolo.

## Griglia (dichiarata) — SUPERSEDED 2026-09-29, vedi DECISIONE in fondo

## Universo: come P1.

## Note
- La metrica che conta: maxDD del nodo vs quello di L sulla stessa finestra. Se non scende
  sotto il 25% la famiglia si archivia.

## CONTESTO 2026-09-29 (dopo P3) — LEGGI PRIMA DI INIZIARE
Il segnale della famiglia canale e' ora dimostrato forte su USDT lunghi (10 majors):
P3 (filtro SMA200, 40g+canale20): expectancy +9,01%/op netta = 16,4x pedaggio, IC90
[+0,10%, +19,12%] positivo, PF 2,01 — bocciata SOLO da t 1,58 e DD 45,5%.
Gli attacchi al DD per USCITA (P1, chandelier) e per REGIME (P3, filtro SMA200) sono
entrambi misurati e insufficienti. Conseguenza operativa per il tuo P2:
- applica il vol targeting alle operazioni della famiglia canale (config riproducibile:
  src/money/ricerca/p3_trend_filtro_200g.py, config 40g|canale20 — oppure Donchian
  55g/20g; la scelta dichiarala);
- NON modificare il segnale: cambia solo quanto si rischia per operazione;
- criterio di successo: maxDD <= 25% mantenendo expectancy >= 3x pedaggio; riporta anche
  l'effetto sul t-stat. Se il DD non scende sotto il 25%, il filone trend si archivia per
  costruzione e si progettano spec nuove sui dati.

## DECISIONE 2026-09-29 (contraddizione risolta, PRIMA del primo numero)
Segnale: **Donchian 55/20 sui 10 majors** (config dell'A/B P1: +7,99%/op netto, DD serializzato
47,0%, DD portafoglio 42,84% — la piu' riproducibile). Il segnale NON si tocca; si cambia solo
il rischio per operazione.
Griglia dichiarata: `vol_target in {0.50, 0.60, 0.75}` x `{sizing si, sizing no}` — il "sizing no"
e' il controllo A/B interno contro il numero noto.
Metrica primaria: **DD DI PORTAFOGLIO mark-to-market** (fix 2026-09-29: il serializzato
sottostima); secondaria: DD serializzato, expectancy, t-stat.
Criterio di successo: DD portafoglio <= 25% E expectancy >= 3x pedaggio. Se non scende sotto il
25%, il filone trend si archivia per costruzione e si progettano spec nuove sui dati.

## ADDENDUM 2026-09-30 (review esterna — PRIMA di ogni numero) — secondarie dichiarate
Oltre al criterio di successo (DD portafoglio <= 25% E expectancy >= 3x pedaggio), si dichiarano
ORA, prima della misura, queste secondarie da riportare (NON bloccanti):
1. costi stressati: terzo scenario con spread+slippage raddoppiati rispetto alla tariffa assunta;
   se in quello scenario l'expectancy scende sotto il pedaggio, va segnalato al direttore prima
   di qualunque promozione;
2. coerenza per regime: DD ed expectancy spezzate per regime di volatilita' (alta/bassa);
3. attrattivita': rapporto expectancy/DD del ramo con sizing NON peggiore di quello del
   controllo "sizing no";
4. riferimento esterno (NON vincolante, non entra nel verdetto): una riduzione relativa del DD
   del 15-35% e' la forbice tipica attesa; serve a contestualizzare, non a promuovere.
