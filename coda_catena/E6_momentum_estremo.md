# E6 — «momentum su estremi di 7 giorni» (pre-registrazione)

**Data:** 2026-10-21 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (regola congelata PRIMA dei numeri su OOS-3)

## Come nasce (dichiarato, senza nascondere il post-hoc)

E5 (mean reversion, z ≤ −3 → long, z ≥ +3 → short) è risultata **negativa su tutti i set**
(train −0,755% t −7,82 · OOS-1 −0,395% t −4,28 · OKX −0,836% t −6,07), e negativa in ogni anno.
Un segnale negativo con t 6–8 non è «nessun edge»: è **la stessa regola col segno opposto**.
La scoperta dell'inversione è quindi **post-hoc** e come tale NON basta: E6 si giudica su un
hold-out mai toccato.

## Ipotesi (congelata)

Quando il prezzo si allontana di 3 deviazioni standard dalla media a 7 giorni, **continua**
invece di rientrare: z ≥ +3 → long, z ≤ −3 → short.

## Regola operativa

- z = (close − SMA168) / stdev168 su barre 1h
- long se z ≥ +3,0 · short se z ≤ −3,0 (specchio esatto di E5)
- cooldown 24 ore per simbolo; ingresso apertura i+1
- uscita: prima barra con |z| ≤ 0,5 **oppure** 72 ore
- stop 3,0 × ATR(14) intrabarra, distanza massima 50%
- costi taker 0,28% RT; stress ×2 = 0,56%; funding non incluso (limite dichiarato)

## Campioni

| Set | Fonte | Ruolo |
| :--- | :--- | :--- |
| TRAIN | Bybit 1h, 57 simboli, 2021-12→2024-05 | coerenza |
| OOS-1 | Bybit 1h, 2024-06→2026-10 | tenuta temporale (già visto in E5) |
| OOS-2 | OKX 1h, 19 simboli, 2024-06→2026-10 | conferma cross-exchange (già visto in E5) |
| **OOS-3** | **Binance 1h, 25 simboli, 2024-06→oggi** | **hold-out pulito: mai usato prima** |

## Criteri (4/4 + DSR)

- T1 **OOS-3 Binance**: media > 0, t ≥ 2,0, n ≥ 30
- T2 OOS-2 OKX: media > 0, t ≥ 2,0
- T3 costi ×2 su OOS-3: media > 0
- T4 TRAIN: media ≥ +0,50%, t ≥ 3,0
- DSR ≥ 0,95 con N = 4 (2 look di E5 + 2 di E6, long/short per ciascuno)

## Se passa

Non è un'autorizzazione: canary 14 giorni a taglia minima con riconciliazione esatta, come C1.
Il sizing parte da 0,25% di rischio per trade (mandato), non da una frazione del capitale.

## Se fallisce

La famiglia «estremi di prezzo» si chiude (E2, E4, E5, E6) e si passa al filone successivo.
