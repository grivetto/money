# P2 — Momentum assoluto con position sizing a volatilita' (vol targeting)
STATO: LIBERA
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

## Griglia (dichiarata, 4 config)
lookback in {60, 90} x vol_target in {0.50, 0.60}

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
