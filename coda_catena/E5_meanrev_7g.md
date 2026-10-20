# E5 — «ritorno alla media a 7 giorni» (pre-registrazione)

**Data:** 2026-10-21 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (scritta PRIMA dei numeri)

## Perché questo filone

Le cascate (E2, E4) sono chiuse: il rimbalzo dopo un crollo violento non regge il cross-exchange.
E5 testa una cosa diversa, non un caso particolare di E4: **la deviazione lenta dal valore medio**.
Non un evento di 3 ore, ma una divergenza costruita in 7 giorni. Se il prezzo si allontana di 3
deviazioni standard dalla sua media settimanale, la storia dei mercati dice che tende a rientrare.

## Ipotesi (congelata)

Su barre 1h, se `z = (close − SMA168) / stdev168` esce da ±3, il rendimento nei successivi
3 giorni è **positivo nella direzione del rientro** (long se z ≤ −3, short se z ≥ +3), al netto
dei costi.

## Regola operativa (nessuna griglia)

- segnale long: z ≤ −3,0 · segnale short: z ≥ +3,0
- cooldown 24 ore per simbolo
- ingresso: apertura della barra i+1
- uscita: chiusura alla prima barra con |z| ≤ 0,5 **oppure** dopo 72 ore (quel che viene prima)
- stop di protezione: 3,0 × ATR(14) intrabarra, distanza massima 50%
- costi: taker 0,28% round-trip; stress ×2 = 0,56%
- funding non incluso (limite dichiarato: su 72h può valere ±0,01–0,10%)

## Campioni

| Set | Fonte | Periodo |
| :--- | :--- | :--- |
| TRAIN | Bybit 1h, 57 simboli | 2021-12 → 2024-05 |
| OOS-1 | Bybit 1h, stessi simboli | 2024-06 → 2026-10 |
| OOS-2 | OKX 1h, 19 simboli (scaricati ex-novo) | 2024-06 → 2026-10 |

## Criteri (4/4 + DSR)

- T1 cross-exchange: OOS-2 media > 0, t ≥ 2,0, n ≥ 30
- T2 tenuta temporale: OOS-1 media > 0, t ≥ 2,0
- T3 costi ×2: OOS-2 stress media > 0
- T4 coerenza train: media ≥ +0,50%, t ≥ 3,0
- DSR ≥ 0,95 con N = 2 look (long e short dichiarati ora)

## Cosa NON è

Non è un griglia di soglie (si testa solo ±3). Non è un'autorizzazione: anche con 4/4 serve il
canary 14 giorni. Se fallisce, la mean reversion lenta si chiude e si passa al filone successivo.

## Artefatti

`scripts/e5_meanrev_7g.py` · `prove/e5_meanrev_7g_2026-10-21.json` · voce nel REGISTRO.
