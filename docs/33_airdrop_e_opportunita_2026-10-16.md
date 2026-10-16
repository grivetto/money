# Airdrop e opportunità — nota onesta (2026-10-16)

*Redatta da Hermes su richiesta dell'owner («ho sentito parlare di airdrop… non ne capisco
nulla»). Questo documento spiega cosa sono, cosa si guadagna davvero, i rischi seri, e cosa
il progetto fa da oggi in merito. Nessuna promessa: solo meccanica e regole.*

---

## 1. Cosa sono (in breve)

Un **airdrop** è una distribuzione gratuita di token da parte di un progetto crypto,
spesso **retroattiva**: chi ha usato il protocollo *prima* che lanciasse il token riceve
una quota (es. aver usato un DEX, un bridge, una chain nuova). È marketing: il progetto
"paga" gli utenti storici per attirare attenzione e liquidità.

## 2. I tre modi in cui si "guadagna" (in ordine crescente di rischio)

1. **Quest e campagne su exchange** (Learn & Earn, concorsi, reward center): piccoli premi
   (qualche USDC, token di nuova quotazione) per quiz o attività. Rischio ≈ zero, richiede
   l'account già esistente (OKX). È la fetta *sicura* del mondo airdrop.
2. **Airdrop passivi**: se un wallet ha usato un protocollo che poi lancia un token, il
   premio arriva da solo. Serve però avere storicità on-chain (noi oggi non l'abbiamo).
3. **Farming on-chain** ("coltivare" l'eleggibilità): usare di proposito protocolli *prima*
   del token (bridge, lending, testnet) sperando nel premio. È qui che stanno **gas spesi,
   capitale bloccato, sforzo anti-sybil e ritorni incerti**. Non è passivo: è un lavoro.

## 3. I rischi seri (da sapere prima di toccare qualunque cosa)

- **Truffe / drainer**: la stragrande maggioranza dei "claim" che circolano sono siti falsi che
  svuotano il wallet. Regola secca: **si firma SOLO su siti ufficiali**, raggiunti da fonti
  ufficiali (blog/annunci del progetto), mai da link ricevuti.
- **Sybil detection**: i progetti escludono gli "agricoltori" scoperti (fondi sprecati).
- **Costo reale**: gas, tempo, capitale immobilizzato in protocolli (rischio smart-contract).
- **FOMO tax**: arrivare tardi = fare i compiti e non prendere il voto.

## 4. Cosa fa il progetto da oggi: il **Radar OKX**

Attivato il **16/10** (`ops/radar/radar_okx.py`, unit utente su mc2, giro ogni 45'):

- legge **solo** il feed ufficiale degli annunci OKX EEA (pubblico, sola lettura, nessuna chiave);
- filtra le voci che possono valere un guadagno a rischio ≈ zero: **Learn & Earn, campagne,
  reward, airdrop, bonus, concorsi, task**;
- notifica le novità sul canale Telegram del progetto (`@DenaroAlertBot`), con dedup
  (baseline silenziosa al primo giro: non arriveranno raffiche di vecchi annunci).

Onesto by design: è un **radar**, non un bottino — mostra le opportunità ufficiali, la
decisione (e la partecipazione) resta umana. Mai link di terzi.

## 5. Se vuoi un pilota on-chain (proposta, in attesa di decisione)

Fattibile in modo disciplinato, così:

- **Wallet nuovo e isolato** (solo per l'esperimento), creato con procedura documentata;
  chiave custodita come le altre del progetto, mai condivisa;
- **Cap: 50–100 €** di gas + capitale, mai dal capitale di trading;
- **Solo protocolli blu** (battle-tested), niente sconosciuti, niente "early";
- ogni tx registrata con motivazione e hash (disciplina del banco a secco);
- **kill-check a 90 giorni**: se non produce nulla di quantificabile, si chiude.

Costo d'ingresso reale: tempo di setup + fee di rete. Guadagno atteso: incerto per natura
(è una scommessa, non una rendita). Per questo la proposta è **opzionale e cappata** —
il percorso principale verso i guadagni resta `ROADMAP.md` (costi → rendita → capitale).

## 6. Stato

- **Fatto**: Radar OKX attivo (questa nota è il suo documento).
- **Da decidere (owner)**: pilota on-chain sì/no (cap 50–100 €) — o si resta sul radar.
- **Mai**: farming con il capitale di trading; firme su wallet principali; link non ufficiali.
