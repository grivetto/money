#!/usr/bin/env python3
"""patch_carry_dashboard.py — aggiunge la card «CARRY LIVE» alla dashboard.

Idempotente. Backup automatico. Mostra: coppie aperte, nozionale, uPL, per coppia
delta ed eta' del dato. Popolata da /api/infra.json -> .carry.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

TARGET = Path("/home/marco/money/ops/dashboard/dashboard_infra.html")

CARD = '''
<!-- CARRY LIVE (16/10/26): DOT+ADA a 90 EUR/gamba, 1x isolated, delta-neutral.
     Popolata da /api/infra.json -> .carry (aggregator). -->
<div class="board" id="board-carry">
  <div class="bd-head">
    <div class="orb" id="orb-carry"></div>
    <div>
      <h2>CARRY LIVE — DELTA-NEUTRAL</h2>
      <div style="font-size:10px;color:var(--dim);letter-spacing:2px" id="c-nota">—</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px">
    <div><div class="k">COPPIE APERTE</div><div class="v" id="c-coppie">—</div></div>
    <div><div class="k">NOZIONALE</div><div class="v" id="c-noz">—</div></div>
    <div><div class="k">uPL</div><div class="v" id="c-upl">—</div></div>
    <div><div class="k">DETTAGLIO</div><div class="v" id="c-dett" style="font-size:11px">—</div></div>
  </div>
</div>
'''

JS = '''
/* ── CARRY LIVE (16/10/26) ── */
function renderCarry(d) {
  const c = (d && d.carry) || {};
  const orb = $('orb-carry');
  if (!c.ok) {
    const e = $('c-nota');
    if (e) e.textContent = c.error ? ('stato carry: ' + c.error) : 'in attesa…';
    if (orb) orb.className = 'orb bad';
    return;
  }
  const stale = (typeof c.age_s === 'number' && c.age_s > 3600);
  if (orb) orb.className = 'orb' + (stale ? ' bad' : '');
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set('c-coppie', (c.coppie_aperte ?? 'n/d'));
  set('c-noz', (c.nozionale_totale_eur != null ? (c.nozionale_totale_eur + ' €') : 'n/d'));
  const upl = c.upl_totale;
  set('c-upl', (upl != null ? (upl >= 0 ? '+' : '') + upl.toFixed(4) : 'n/d'));
  const cp = c.coppie || {};
  const righe = Object.keys(cp).map(n => {
    const v = cp[n] || {};
    const dl = (v.delta != null) ? v.delta.toFixed(4) : '?';
    return n + ' ' + (v.aperta ? '●' : '○') + ' lev' + (v.leva || '?') + ' Δ' + dl;
  });
  set('c-dett', righe.join(' · ') || 'n/d');
  const n = $('c-nota');
  if (n) n.textContent = 'aggiornato ' + Math.round((c.age_s || 0) / 60) + "' fa"
    + ' · funding carry ~5-7%/anno · leva 1x';
}
'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERRORE: {TARGET} non trovato")
        return 1
    t = TARGET.read_text(encoding="utf-8")
    if "renderCarry" in t:
        print("card carry esiste gia': nessuna modifica")
        return 0

    bak = TARGET.with_suffix(f".html.bak-carry-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(TARGET, bak)

    # 1. card: dopo la board della ricerca
    idx = t.find('<div class="board" id="board-ricerca">')
    if idx < 0:
        print("ERRORE: board-ricerca non trovata")
        return 1
    fine = -1
    for m in ('\n  <div class="board"', '\n  <div class="card"', '\n  <div class="grid"',
              '\n  <div id="prices"'):
        pos = t.find(m, idx + 10)
        if pos > 0 and (fine < 0 or pos < fine):
            fine = pos
    if fine < 0:
        print("ERRORE: fine board-ricerca non trovata")
        return 1
    t = t[:fine] + "\n" + CARD + t[fine:]

    # 2. JS prima di </script>
    t = t.replace("</script>", JS + "\n</script>", 1)

    # 3. chiamata: SOLO alla riga di chiamata (non alla definizione)
    chiamata = "\n    renderRicerca(d);"
    if chiamata in t:
        t = t.replace(chiamata, "\n    renderRicerca(d);\n    renderCarry(d);", 1)
    else:
        print("ATTENZIONE: riga 'renderRicerca(d);' non trovata — aggiungere a mano")

    TARGET.write_text(t, encoding="utf-8")
    print(f"OK: card CARRY LIVE inserita | backup: {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
