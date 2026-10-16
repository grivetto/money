#!/usr/bin/env python3
"""patch_ricerca_dashboard.py — aggiunge la sezione «RICERCA EDGE» alla dashboard.

Idempotente, backup automatico. Inserisce:
  1. una card HTML (con id="ricerca") dopo la card della board del canary;
  2. la funzione renderRicerca(d) e la sua chiamata in update().
Mostra: promosse/archiviate, esito review C1, funding scan, verdetti P15 e nodo E.
Nessun numero inventato: se manca un dato scrive «n/d».
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

TARGET = Path("/home/marco/money/ops/dashboard/dashboard_infra.html")

CARD = '''
<!-- RICERCA EDGE (15/10/26): i verdetti degli esperimenti misurati — C1, P15, nodo E,
     funding scan. Popolata da /api/infra.json → .ricerca (aggregator). -->
<div class="board" id="board-ricerca">
  <div class="bd-head">
    <div class="orb" id="orb-ric"></div>
    <div>
      <h2>RICERCA EDGE — VERDETTI MISURATI</h2>
      <div style="font-size:10px;color:var(--dim);letter-spacing:2px" id="r-nota">—</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:12px">
    <div><div class="k">PROMOSSE</div><div class="v" id="r-promosse">—</div></div>
    <div><div class="k">ARCHIVIATE</div><div class="v" id="r-archiviate">—</div></div>
    <div><div class="k">REVIEW C1</div><div class="v" id="r-c1">—</div></div>
    <div><div class="k">FUNDING SCAN</div><div class="v" id="r-funding">—</div></div>
    <div><div class="k">P15 · MVRV</div><div class="v" id="r-p15">—</div></div>
    <div><div class="k">NODO E · BASIS</div><div class="v" id="r-basis">—</div></div>
  </div>
</div>
'''

JS = '''
/* ── RICERCA EDGE (15/10/26) ── */
function renderRicerca(d) {
  const r = (d && d.ricerca) || {};
  if (!r.ok) {
    const el = $('r-nota');
    if (el) el.textContent = r.error ? ('stato ricerca: ' + r.error) : 'in attesa…';
    return;
  }
  const set = (id, val) => { const e = $(id); if (e) e.textContent = val; };

  set('r-promosse', (r.promosse ?? 'n/d'));
  set('r-archiviate', (r.archiviate ?? 'n/d'));

  const rc = r.review_c1 || {};
  const tf = rc.checklist || {};
  const pass = Object.values(tf).filter(v => v === 'PASS').length;
  const tot = Object.keys(tf).length;
  set('r-c1', tot ? (pass + '/' + tot) : 'n/d');

  const fs = r.funding_scan || {};
  if (fs.disponibile && fs.miglior_netto != null) {
    const pct = (fs.miglior_netto * 100).toFixed(1) + '%';
    set('r-funding', (fs.miglior || '?') + ' ' + pct);
  } else set('r-funding', 'n/d');

  const p15 = r.p15_mvrv || {};
  set('r-p15', p15.verdetto || (p15.disponibile ? 'n/d' : 'non misurata'));

  const be = r.nodo_e_basis || {};
  set('r-basis', be.verdetto || (be.disponibile ? 'n/d' : 'non misurato'));

  const el = $('r-nota');
  if (el) {
    const eta = (typeof r.age_s === 'number') ? Math.round(r.age_s / 60) + "' fa" : '—';
    el.textContent = 'aggiornato ' + eta +
      ' · C1 = canary carry DOGE (review PASS) · il carry funding è l\\'unico filone vivo';
  }
}
'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERRORE: {TARGET} non trovato")
        return 1
    testo = TARGET.read_text(encoding="utf-8")
    if "renderRicerca" in testo:
        print("sezione ricerca esiste gia': nessuna modifica")
        return 0

    bak = TARGET.with_suffix(f".html.bak-ricerca-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(TARGET, bak)

    # 1. card HTML: dopo il blocco della board canary. La board chiude con
    #    "</div>\n  </div>" prima del blocco successivo: ancoro all'inizio del
    #    div successivo per essere robusto.
    idx = testo.find('<div class="board" id="board">')
    if idx < 0:
        print("ERRORE: board canary non trovata")
        return 1
    # la board finisce all'inizio del div successivo di pari livello:
    # cerco la riga "  <div class=\"board\"" successiva, oppure il marcatore noto.
    fine = -1
    for marcatore in ('\n  <div class="board"', '\n  <div class="card"',
                      '\n  <div class="grid"', '\n  <div id="prices"'):
        pos = testo.find(marcatore, idx + 10)
        if pos > 0 and (fine < 0 or pos < fine):
            fine = pos
    if fine < 0:
        print("ERRORE: fine board canary non trovata")
        return 1
    testo = testo[:fine] + "\n" + CARD + testo[fine:]

    # 2. JS: prima del tag di chiusura script
    if "</script>" not in testo:
        print("ERRORE: </script> non trovato")
        return 1
    testo = testo.replace("</script>", JS + "\n</script>", 1)

    # 3. chiamata in update(): SOLO alla riga di chiamata, non alla definizione.
    #    (Il patch precedente aveva colpito `function renderBoard(d) {` corrompendo
    #    la dichiarazione: qui si sostituisce la chiamata con la sua indentazione.)
    chiamata = "\n    renderBoard(d);"
    if chiamata in testo:
        testo = testo.replace(chiamata, "\n    renderBoard(d);\n    renderRicerca(d);", 1)
    else:
        print("ATTENZIONE: chiamata '    renderBoard(d);' non trovata — aggiungere a mano")

    TARGET.write_text(testo, encoding="utf-8")
    print(f"OK: sezione RICERCA EDGE inserita | backup: {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
