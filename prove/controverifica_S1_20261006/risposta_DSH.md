## REQ-20261006-202344-5433843 | 2026-10-06T20:26:18Z | DONE

Contro-verifica indipendente (DSH/omarchy): ricalcolo da zero di mom_abs/rsi2, segnali e costi re-implementati da specifica (nessun import money).
RIPRODUZIONE: tutti e 5 i top ufficiali identici al 7o decimale (n, exp, t) - es. DOGE mom20 n=35 exp +6,80% t=0,865; XRP rsi2(3,15,65) n=32 exp +2,54% t=1,712. Pipeline S1 aritmeticamente corretta.
VERDETTO mom_abs (4 casi): NON reggono. P2 [2025-07-01,fine] piatto/negativo (+0,06 / +0,04 / -2,02 / -0,50%), CI90 block bootstrap (10 op, 2000 iter) include lo zero, DSR <= 0,10. Code di selezione, non edge. No escalation.
VERDETTO rsi2(3,15,65) XRP: regge la robustezza descrittiva (P1 +3,71%, P2 +1,64%; CI90 [+0,78%,+4,02%], stabile su piu' seed; costi x2 exp +2,28% t=1,54). Ma n=32, t=1,71<2, DSR=0,36 << 0,95: al massimo esperimento pre-registrato MIRATO, non candidato.
CONFERMA esito ufficiale 0 candidati (DSR<0,95). Nessuna divergenza numerica; nessun bug di calcolo.
DISCREPANZA DA SANARE (dichiarazione): il registro dichiara FINE_STORIA=2026-09-25, ma i numeri ufficiali si riproducono solo usando le barre fino al 2026-10-05. Impatto sui verdetti nullo (+-1 operazione), ma la finestra va allineata.
COSTI usati (come da scansione, piu' conservativi del testo task): pedaggio giro misto okx_eea_con_perp 0,18%/round-trip + slippage 0,04%/lato moltiplicativo = ~0,26% all-in; costi doppi = 0,52% all-in. Variante letterale task (~0,18% all-in) riportata in tabella.
Artefatti: ~/dsh-scratch/s2-review/controverifica.py, verdetto.md, RISPOSTA.md.
