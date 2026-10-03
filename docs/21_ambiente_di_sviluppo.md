# 21 — Ambiente di sviluppo v2 (flotta esecutori)

Data: 2026-10-04 (notte). Stato: operativo.

## La flotta — 11 esecutori su 4 macchine + regia

| Esecutore | Macchine | Guida | Note |
|---|---|---|---|
| **Hermes** (regia) | mc2 | — | spec, review, integrazione, misure ufficiali, commit: mai delegati |
| **A0** (Agent Zero v2.13) | mc2, win | `tools/a0_dispatch.py` | esecutori storici, brief inline |
| **opencode** | **4 nodi** (mc2, omarchy, nuvola, MARCODG1) | `opencode run -m <modello> --auto` | operaio coding free; default **`opencode/ling-3.1-flash-free`** (small: `nemotron-3.5-lightning-free`); smoke PONG su tutti il 04/10; v2.0.22 su nuvola/MARCODG1, v1.18.34 su mc2/omarchy (upgrade opzionale) |
| **agy** (Antigravity CLI) | mc2 (1.2.11 snap), omarchy/nuvola/MARCODG1 (1.2.16) | `agy -p "<task>" --output-format json` | operaio coding/analisi; allowlist command+read/write; deny segreti/git push; **MARCODG1: write solo in `~/agy-scratch`** |
| **DSH** (DeepSeek Harness) | mc2 (`dsh-web` :4080 + headless), omarchy (web :5080, canale `dsh-mc2/`), win (web :3080, canale `dsh/`) | headless locale / canali file | peer ricerca; porte standardizzate 03/10 |

## Pipeline di lavoro (una lane = spec → consegna → review → commit)
1. **Spec** autosufficiente → `spec_lint` 7/7 + JEV gate (advisory) PRIMA del dispatch.
2. **Dispatch** a un esecutore: lavoro SEMPRE in scratch per-nodo (`~/agy-scratch`, `~/dsh-scratch`, …); repo in sola lettura.
3. **Consegna = pacchetto sigillato PROTCON** (`MANIFEST.sha256` + `READY` per ultimo; chiave = sha256 del manifest) — niente consegne a mano.
4. **Verifica Hermes**: hash byte-exact (corsia Windows: `tr -d '\r' < MANIFEST.sha256 | sha256sum -c -`), py_compile, test nel repo, review.
5. **Integrazione**: copia → suite completa + ruff → commit `[hermes]` (con provenienza) → push → MSG di esito sul canale.

## Regole di flotta (non negoziabili)
- MAI `--dangerously-skip-permissions`; permessi via allowlist esplicita; deny-list per segreti (`**/.env*`, `.ssh`, token), `.git`, `git push/commit/reset --hard`.
- **Modelli: solo online (API) — niente inference locale nella flotta** (decisione owner, 04/10; colibrì/GLM-5.2 valutato e scartato: 0,05–2 tok/s non regge i loop agentici).
- Un free tier condiviso su tutte le macchine ⇒ niente ondate parallele identiche (429); riserva pronta.
- Agenti MAI sul percorso del capitale: ordini/servizi solo Hermes; MARCODG1 = produzione (write confinato).
- Zero silenzi: ogni consegna ha ACK/DONE/FAILED; ogni componente critico ha heartbeat.

## Prossimi passi
- Adozione PROTCON nel tick: `verify(dir)` + `idempotency_key "handoff:"+key` (`fabbrica/handoff_atomico.py`).
- Allineare versioni opencode su mc2/omarchy (1.18.34 → 2.0.22; richiede OK owner, sui nodi il comando di upgrade è gated).
- `job_duration` (dai claim automatizzati).
