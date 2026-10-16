#!/usr/bin/env python3
"""radar_okx.py — radar delle opportunità sugli annunci ufficiali OKX (EEA).

Legge il feed pubblico degli annunci (nessuna chiave, sola lettura), filtra le
voci che possono valere un guadagno a rischio ~zero (Learn & Earn, campagne,
reward, airdrop, bonus, concorsi, task) e le notifica sul canale Telegram del
progetto. Dedup su ~/.radar_okx/seen.json (baseline silenziosa al primo giro).

Onesto by design: è un radar, non un bottino — la decisione (e l'eventuale
partecipazione) resta umana. Legge SOLO il feed ufficiale OKX, mai link di terzi.

Uso:  radar_okx.py run [--forza]   # fetch + notifica novità (--forza: manda anche il primo giro)
      radar_okx.py --dry          # stampa, non notifica, non aggiorna lo stato
Exit: 0 ok · 2 fetch fallito.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
URL = "https://eea.okx.com/api/v5/support/announcements"
STATO = Path.home() / ".radar_okx" / "seen.json"
CHIAVI = ("learn & earn", "learn and earn", "learn&earn", "airdrop", "reward",
          "campaign", "bonus", "giveaway", "competition", "task", "promo")
MAX_ETA_GIORNI = 45
MAX_VISTI = 800


def fetch(timeout: int = 20, url: str = URL) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "money-radar-okx"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def estrai(dati: dict) -> list[dict]:
    fuori: list[dict] = []
    for gruppo in dati.get("data") or []:
        for det in gruppo.get("details") or []:
            titolo = det.get("title") or ""
            url = det.get("url") or ""
            if not titolo or not url:
                continue
            try:
                ts = float(det.get("pTime") or 0) / 1000.0
            except (TypeError, ValueError):
                ts = 0.0
            fuori.append({"titolo": titolo, "url": url, "tipo": det.get("annType") or "",
                          "ts": ts})
    return fuori


def filtra(items: list[dict], chiavi: tuple[str, ...] = CHIAVI) -> list[dict]:
    return [i for i in items if any(k in i["titolo"].lower() for k in chiavi)]


def carica_visti(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("visti") or {}
    except Exception:  # noqa: BLE001
        return {}


def salva_visti(path: Path, visti: dict) -> None:
    if len(visti) > MAX_VISTI:
        for k in sorted(visti, key=lambda x: visti[x])[: len(visti) - MAX_VISTI]:
            visti.pop(k, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"visti": visti}, ensure_ascii=False), encoding="utf-8")


def nuovi_da_notificare(items: list[dict], visti: dict, adesso: float | None = None,
                        max_giorni: int = MAX_ETA_GIORNI) -> list[dict]:
    adesso = adesso or time.time()
    return [i for i in items if i["url"] not in visti
            and (not i["ts"] or adesso - i["ts"] <= max_giorni * 86400)]


def _invia(testo: str) -> bool:
    try:
        sys.path.insert(0, str(REPO / "ops" / "alerts"))
        import notifica_tg  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        return notifica_tg.invia(testo)
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Radar opportunità OKX (feed ufficiale)")
    ap.add_argument("comando", nargs="?", default="run", choices=["run"])
    ap.add_argument("--dry", action="store_true", help="stampa senza notificare né scrivere")
    ap.add_argument("--forza", action="store_true", help="ignora la baseline del primo giro")
    ap.add_argument("--stato", default=str(STATO))
    args = ap.parse_args(argv)
    stato = Path(args.stato)

    try:
        dati = fetch()
    except Exception as e:  # noqa: BLE001
        print(f"radar: fetch fallito ({e.__class__.__name__})")
        return 2

    items = filtra(estrai(dati))
    visti = carica_visti(stato)
    prima_volta = not stato.exists() and not args.forza
    if prima_volta:
        print(f"radar: prima esecuzione — baseline salvata ({len(items)} voci pertinenti)")
        if not args.dry:
            for i in items:
                visti[i["url"]] = time.time()
            salva_visti(stato, visti)
        return 0

    nuovi = nuovi_da_notificare(items, visti)
    if args.dry:
        for i in nuovi:
            print(f"  • {i['titolo']}\n    {i['url']}")
        print(f"radar(dry): {len(nuovi)} novità su {len(items)} voci pertinenti")
        return 0

    if nuovi:
        testo = (f"\U0001F6F0\uFE0F Radar OKX — {len(nuovi)} novità:\n"
                 + "\n".join(f"\u2022 {i['titolo']}\n  {i['url']}" for i in nuovi[:8]))
        inviato = _invia(testo)
        print(f"radar: {len(nuovi)} novità — notifica {'inviata' if inviato else 'non inviata (spool)'}")
    else:
        print(f"radar: nessuna novità (su {len(items)} voci pertinenti)")
    for i in items:
        visti[i["url"]] = visti.get(i["url"], time.time())
    salva_visti(stato, visti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
