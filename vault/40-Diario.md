# Diario del progetto

## 2026-09-27 — La coda e il primo "6/8"
- Costruita la coda `coda_catena/` (spec P1–P4) e riorganizzato il canale DSH.
- P1 (chandelier ATR) misurata e archiviata: lo stop in uscita **peggiora** tutto.
- Nell'A/B di P1 la scoperta: **Donchian su 10 majors USDT = 6/8 criteri** (IC90 positivo per la prima volta nel progetto).

## 2026-09-28 — P5, il ridimensionamento onesto
- P5 (Donchian su 61 coppie): l'edge **non regge** l'allargamento (t 1,44; DD 98,9%). Meglio saperlo ora.
- Agent Zero riparato e messo al lavoro su P3. P4 parcheggiata (funding: 96 giorni di storia).

## 2026-09-29 — P3 e la sala di controllo
- Consegna P3 di Agent Zero: non valida (bug bloccanti). Hermes riscrive il modulo → 10 test nuovi → suite **218/218** verde.
- P3 misurata: di nuovo **6/8**. Expectancy +9,01%/op (16,4×), IC90+, PF 2,01 — ma DD 45,5% e t 1,58. **Il filtro di regime non doma il DD.**
- Creata questa sala di controllo (vault Obsidian, mc2 + Windows).

## 2026-10-03 — La squadra al completo
- **DSH ora gira anche su mc2 come servizio** (`dsh-web` :3080, systemd; headless collaudato con PONG-MC2): esecutore in più, in casa.
- **Nodo agenti a 3 esecutori**: opencode ricollaudato (PONG-OC) + **agy/Antigravity** in squadra.
- Foto della squadra: `money/FOTO_SQUADRA_2026-10-03.png` (8 esecutori + regia, su 3 macchine).
- Contorno: canary C1 in validazione (review 15/10) · capitale ≈1.100 € · P10 "insufficiente" (23<30 op).
