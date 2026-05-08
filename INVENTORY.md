# Denaro Infrastructure Inventory — Source of Truth
**Last updated:** 2026-04-28 | **Maintained on:** mc2

## Legend
- Status: ✅ Online / ⚠️ Degraded / ❌ Offline / 🔄 Syncing
- API Keys: SEPARATE per node (no cross-use)

| Node | IP | Role | Bot Script | Startup Method | API Key | Balance (EUR) | Balance (SOL) | Last Checked | Status | Notes |
|------|----|------|------------|----------------|---------|---------------|---------------|--------------|--------|-------|
| mc2 | — | Controller / Git source | `denaro_ultimate.py` (golden) | — | — | — | — | 2026-04-28 | ✅ Clean source | SCP source to workers |
| MARCODG1 | 87.106.222.123 | Worker (systemd) | `grid_bot_v3.py` | systemd (sudo) | Key_Marco | 39.02 | 0.0 | 2026-04-28 | ✅ Active | PID 287028, 3 ordini SOLEUR |
| nuvola | 87.106.3.15 | Worker (screen) | `grid_bot_v3.py` | screen | Key_Sergio | 39.02 | 0.0 | 2026-04-28 | ❌ Down | rete offline |

---

## Golden Files (on mc2)
```bash
/home/sergio/denaro/
├── grid_bot_v3.py.golden    ← Source pulito (333 linee, checksum cd9f52e...)
├── grid_config.json          ← Config di riferimento (SOL/EUR, 10€ order)
├── denaro_ultimate.py        ← Source antico (non usato)
├── systemd/
│   └── denaro-grid.service   ← Systemd unit (per MARCODG1-style nodes)
├── launch_denaro.py          ← Launcher universale (screen/systemd)
├── health_check.py           ← Health monitor script
├── recover_denaro_node.sh    ← Recovery script automatico
└── INVENTORY.md              ← Questo file
```

---

## Recovery Procedures

### A. Nuvola — When network returns
```bash
# Su mc2 (controller):
cd /home/sergio/denaro
bash recover_denaro_node.sh nuvola

# Se recover_denaro_node.sh non disponibile, manuale:
ssh 87.106.3.15
pkill -f grid_bot; screen -S denaro -dm /home/sergio/denaro/venv/bin/python /home/sergio/denaro/grid_bot_v3.py
```

### B. MARCODG1 — Restart systemd
```bash
ssh MARCODG1 "sudo systemctl restart denaro-grid.service && sudo systemctl status denaro-grid.service"
```

### C. Full infrastructure audit
```bash
python3 health_check.py all
```

---

## Configuration Reference

### grid_config.json (current)
```json
{
  "SYMBOLS": ["SOLEUR"],
  "GRID_LEVELS": 6,
  "GRID_SPACING": 0.01,
  "ORDER_SIZE_EUR": 10.0
}
```

### Known Issues
1. **nuvola offline** → wait for network restoration
2. **trades.db non creato** → aspetta primo trade completato
3. **Logging locale non funziona** → usa `journalctl -u denaro-grid -f` su MARCODG1

---

## Contacts
- **mc2** (controller): `sergio`
- **MARCODG1** (worker): `marco`
- **nuvola** (worker): `sergio`

---

## Changelog
- **2026-04-28** — System fully recovered: MARCODG1 active, nuvola offline, config externalized
- Golden source established on mc2 + MARCODG1
- Systemd adopted, instances deduped, DB reset
