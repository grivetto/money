# P3 — Trend con filtro di regime 200 giorni
STATO: PRESA_DA agent-zero 2026-09-27
DATI: USDT-lungo (2019-01-01 -> oggi; confine 2024-06-01)

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
