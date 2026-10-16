# ROADMAP — dai 1.096 € ai guadagni reali

**16/10/2026 · documento di decisione · owner: Sergio · regia: Hermes**
*(numeri verificati stasera: equity 1.096 € riconciliata, motore = Simple Earn + carry delta-neutral, costi stimati ≈31 €/mese)*

---

## 0. Il punto, senza sconti

Oggi la macchina **rende ≈3,4 €/mese e costa ≈31 €/mese → ≈ −28 €/mese (≈ −335 €/anno)**.
Non è colpa del trading (disciplinato e fermo): è **aritmetica**.

- Rendita possibile con questo capitale, a rischio basso (5–6,5%/anno): ≈ **3–5 €/mese**.
- Costi di gestione: ≈ **31 €/mese** (VPS ≈9 + AI ≈22, da confermare).

Con 1.096 € l'unico modo di non perdere è **cambiare l'aritmetica**: (1) tagliare i costi,
(2) mettere a lavorare ogni euro dormiente, (3) crescere il capitale solo con evidenza.
Questa roadmap fa questo, per fasi, con gate e kill-criteria. Ogni fase ha un numero.

## 1. I numeri veri (stasera)

| Voce | Valore | Nota |
| :--- | ---: | :--- |
| Capitale | **1.096 €** | OKX EEA, riconciliato (banco read-only) |
| — Simple Earn | 534 € | USDC ≈ 5,6%/anno, riscatto istantaneo |
| — funding account | 194 € | **a rendimento ZERO** ← da svegliare |
| — comparto trading | 368 € | di cui buona parte è collaterale del carry |
| Carry (reale) | 180 € nozionale | DOT+ADA delta-neutral, ≈5–6,5%/anno netti attesi |
| Canary C1 | ≈10 $ | DOGE delta-neutral, review 14 giorni **PASS** |
| Rendita attuale | ≈ **3,4 €/mese** | Earn ≈2,5 + carry ≈0,9 |
| Costi | ≈ **31 €/mese** | VPS ≈9 + AI ≈22 (da confermare con te) |
| **Netto** | **≈ −28 €/mese** | **il numero da uccidere** |

Fee di trading: contate e incluse in ogni misura (criterio del cancello: rendita ≥ 3× pedaggio).

**Break-even** (rendita = costi, a ≈5,5% netto):

| Costi/mese | Break-even |
| ---: | ---: |
| 31 € (oggi) | ≈6,8 k€ |
| 16 € (dopo D1) | ≈3,5 k€ |
| 9 € (solo VPS) | ≈2,0 k€ |
| ≤6 € (VPS minimo) | ≈1,3 k€ |

## 2. FASE 0 — questa settimana: tre decisioni tue

**D1 · Taglio costi** *(il guadagno più grande e immediato: 1 € tagliato = 1 € di rendita, garantito)*
- AI ≈22 €/mese: è un costo **del progetto**? Se sì → tier inferiore / consumo / modelli free
  (gli operai girano già in gran parte su free). Target ≤ 10 €/mese.
- VPS ≈9 €/mese: valutare consolidamento (nuvola→MARCODG1?) tenendo i vincoli reali:
  whitelist IP OKX, monitoraggio di mc2 (macchina di casa), nodo paper. Target ≤ 6 €/mese.
- **Obiettivo: da ≈31 a ≤16 €/mese** → vale ≈180 €/anno, oltre 4× la rendita annua attuale.

**D2 · Ogni euro dormiente si sveglia** *(rischio aggiuntivo ≈ zero)*
- 194 € nel funding a 0% → **Simple Earn**: +≈11 €/anno, subito.
- Comparto trading: calcolo il collaterale minimo del carry + riserva operativa (≈100 €)
  e sposto **l'eccesso** in Earn (importo esatto prima di muovere qualunque cosa).
- Effetto: rendita **+≈1 €/mese** senza nuovo rischio.

**D3 · Carry a scala regolata** *(l'unico motore con evidenza)*
- Da 180 € → **400 €** di nozionale, a step di +100 €, solo con gate verdi:
  funding medio 7g ≥ 2%/anno netto per coppia · nessuna inversione continua >24h ·
  distanza di liquidazione ≥ 40% · banco riconciliato. **Stop al primo rosso.**
- Atteso: +≈20 €/anno. Cap: carry ≤ 30% del capitale.

## 3. FASE 1 — entro fine novembre: la macchina si prende cura di sé

- **Report mensile automatico** (lo implemento io, sul canale Telegram già attivo): capitale,
  rendita realizzata, costi, netto, incidenti, decisioni richieste. **Il tuo tempo: ≤15 min/mese.**
- **Track record**: 60 giorni di Earn+carry senza incidenti, tutto riconciliato, fee contate.
- KPI settimanali nel digest: rendita netta (€) · fee · distanza dal break-even.
- Nota cambio $: il totale in € può muoversi ±2–3% col cambio, più della rendita annua.
  Il digest lo scompone (cambio vs resto). Politica attuale: **si resta in $**; se servirà
  stabilità in € a 6–12 mesi se ne parla a parte.

## 4. FASE 2 — da metà dicembre: scala il capitale, non il rischio

Prima review di scala: **≈15/12** (60 giorni dal via del carry multi). Se il track record è
pulito, l'owner valuta versamenti a step (**+1k → +2k → +5k…**), a **motore invariato**
(Earn + carry + eventuale edge nuovo passato dal cancello). Proiezioni oneste, netto di costi
tagliati a ≈10–16 €/mese:

| Capitale | Rendita ≈5,5% | Netto stimato |
| ---: | ---: | ---: |
| 2 k€ | ≈9 €/mese | ≈ −1 … 0 (pareggio col solo VPS) |
| 5 k€ | ≈23 €/mese | ≈ +8 … +13 €/mese |
| 10 k€ | ≈46 €/mese | ≈ +30 … +36 €/mese |
| 25 k€ | ≈115 €/mese | ≈ +100 €/mese |
| 50 k€ | ≈229 €/mese | ≈ +180 €/mese |

*È il pavimento a rischio basso, non il tetto: cresce col capitale, o con un edge che oggi non esiste.*

## 5. FASE 3 — la ricerca (già pagata, costo marginale ≈0)

Il loop giornaliero continua da solo (0 candidati finora, soglia DSR 0,95 — meglio zero che
rumore). Regole: **1 filone alla volta**, pre-registrato, passaggio dal cancello a 8 criteri,
**mai live senza PASS**. Se emerge un edge migliore del carry, entra nella Fase 2 col suo motore.

## 6. L'orologio e i kill-criteria (per non perdere TEMPO)

- Il sistema deve costare **≤15 min/mese** del tempo di Sergio. Se chiede di più e non è un
  incidente → è un bug di progettazione: lo sistemo io.
- **Kill-check 31/01/2027**: se dopo i tagli e 90 giorni la rendita netta è ancora ≤0 e nessun
  edge è emerso → **modo manutenzione** (solo Earn, costi ≈0, capitale intatto, zero tempo).
  Nessuna vergogna: è un numero, non un fallimento.
- **Vietato per statuto**: alzare il rischio per "recuperare" · strategie senza gate ·
  nuovi costi senza ROI calcolato · promesse.

## 7. Le 3 decisioni di oggi (risposta secca)

1. **D1 costi** — taglio AI a ≤10 €/mese (se costo di progetto) e valutiamo il consolidamento VPS?
2. **D2 dormienti** — ok a spostare nei prossimi giorni i 194 € del funding + l'eccesso trading
   (con riserva operativa) in Simple Earn?
3. **D3 carry** — ok a scalare a 400 € a step, con i gate dichiarati sopra?

**Effetto delle decisioni** (stimate, su base annua): D1 ≈ +180 € · D2 ≈ +13 € · D3 ≈ +20 €.
Con tutte e tre: il netto passa da **≈ −28 a ≈ −10 €/mese**; il resto lo fanno i tagli profondi
(≤6 €/mese) o il capitale (≈2 k€ per il pareggio col solo VPS; ≈3,5 k€ con D1 attuata).
