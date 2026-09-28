# P3 — Trend con filtro di regime 200 giorni
STATO: FATTA 2026-09-29 — integrata da hermes (consegna agent-zero non valida: modulo
riscritto, vedi site/projects/denaro-p3/REVIEW3.md). ESITO: ARCHIVIATA (6/8).
DATI: USDT-lungo (2020-10-01 -> 2026-09-25; confine 2024-06-01) — finestra allineata a P1.

## Esito (2026-09-29)
Verifica: 45 ops in 846gg, expectancy netta +9,01% (16,4x pedaggio), IC90 [+0,10%, +19,12%]
positivo, PF 2,01, EUR/anno +437 su 1000 EUR. Bocciata da: t 1,58 (soglia 1,65) e maxDD
45,5% (soglia 25%). A/B Donchian pura stessa finestra: +7,99%/op, DD 47,0%.
LETTURA: il filtro di regime NON riduce il DD (45,5% vs 47,0%): il drawdown non nasce dai
trade in regime ribassista ma dalla sequenza/sizing delle operazioni. Il segnale resta il
piu' forte del progetto (expectancy e IC sopra il Donchian puro). Resta UN solo attacco al
DD: il sizing (P2, in corso). Prove: prove/P3_trend_filtro_200g.{txt,json}.

## Ipotesi
Il trend-following fallisce nei mercati laterali/ribassisti perche' compra rotture che non
seguono. Filtro classico: si compra il breakout SOLO se la chiusura e' sopra la media a 200
giorni (regime toro strutturale). Sotto la media: niente trade. Con la storia USDT lunga
(7+ anni) il filtro ha due regimi veri da dimostrare (2021 toro, 2022 orso).

## Meccanica
- Entrata: chiusura(i) > max(massimi[i-N .. i-1]) E chiusura(i) > SMA200(i) -> apertura i+1.
- Uscita: rottura del minimo a 20 giorni (chiusura sotto min(minimi[j-21 .. j-2])) ->
  apertura j. Oppure chiusura sotto SMA200 -> apertura j (prima delle due).
- Una posizione alla volta; anti-look-ahead identico agli altri nodi.

## Griglia (dichiarata, 4 config)
N in {20, 40} x {uscita a canale 20g, uscita a SMA200}

## Universo: come P1.

## Note
- La trappola da evitare: SMA200 sul giornaliero con storia dal 2019 lascia ~2.200 barre
  utili dopo il riscaldamento. Controllare che la verifica abbia comunque n >= 30.
