"""Preflight: ogni controllo dice il perche', e le eccezioni di rete sono fallimenti, non crash."""


class StubExchange:
    def __init__(self, perm="read_only,trade", mercati=None, eur_libero=0.0,
                 esplodi_mercati=False, esplodi_saldo=False):
        self._perm = perm
        self._mercati = mercati if mercati is not None else {
            "BTC/EUR": {"active": True, "limits": {"cost": {"min": 1.0}}}}
        self._eur = eur_libero
        self._esplodi_mercati = esplodi_mercati
        self._esplodi_saldo = esplodi_saldo

    def privateGetAccountConfig(self):
        return {"data": [{"perm": self._perm}]}

    def load_markets(self):
        if self._esplodi_mercati:
            raise ConnectionError("giu'")
        self.markets = self._mercati

    def fetch_balance(self, _params):
        if self._esplodi_saldo:
            raise ConnectionError("giu'")
        return {"EUR": {"free": self._eur, "total": self._eur, "used": 0.0}}


from money.esecuzione.preflight import preflight


def test_tutto_ok_passa():
    esito = preflight(StubExchange(eur_libero=50.0), "BTC/EUR", 10.0)
    assert esito.ok and esito.motivi_rifiuto() == []


def test_saldo_deve_coprire_nozionale_piu_fee():
    """10 EUR di ordine con 10,00 EUR liberi fallisce per la fee taker."""
    esito = preflight(StubExchange(eur_libero=10.0), "BTC/EUR", 10.0)
    assert not esito.ok
    assert any("saldo" in m for m in esito.motivi_rifiuto())
    # con 10,04 invece passa (fee 0,35% su 10 = 0,035)
    assert preflight(StubExchange(eur_libero=10.04), "BTC/EUR", 10.0).ok


def test_simbolo_assente_blocca():
    esito = preflight(StubExchange(mercati={}), "BTC/EUR", 10.0)
    assert not esito.ok and any("simbolo" in m for m in esito.motivi_rifiuto())


def test_simbolo_disabilitato_blocca():
    esito = preflight(StubExchange(
        mercati={"BTC/EUR": {"active": False, "limits": {}}}), "BTC/EUR", 10.0)
    assert not esito.ok


def test_chiave_read_only_blocca_un_ordine():
    """La chiave del banco non deve MAI poter inviare: il preflight lo dice."""
    esito = preflight(StubExchange(perm="read_only", eur_libero=50.0), "BTC/EUR", 10.0)
    assert not esito.ok and any("permessi" in m for m in esito.motivi_rifiuto())


def test_rete_giu_e_un_fallimento_non_un_crash():
    esito = preflight(StubExchange(esplodi_saldo=True), "BTC/EUR", 10.0)
    assert not esito.ok and any("saldo" in m for m in esito.motivi_rifiuto())


def test_min_notional_dal_mercato_vince_sulla_config():
    esito = preflight(StubExchange(
        mercati={"BTC/EUR": {"active": True, "limits": {"cost": {"min": 5.0}}}},
        eur_libero=50.0), "BTC/EUR", 3.0, min_notional_cfg=1.0)
    assert not esito.ok and any("min_notional" in m for m in esito.motivi_rifiuto())
