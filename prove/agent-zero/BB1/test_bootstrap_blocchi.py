"""
Test per bootstrap_blocchi.py
Almeno 6 test con ASSERT vere.
"""

import sys
import math
sys.path.insert(0, '/a0/usr/workdir')

from bootstrap_blocchi import ic90_blocchi, sensibilita


def test_determinismo():
    """(a) Due chiamate con stesso seme => stessi estremi."""
    serie = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    ic1 = ic90_blocchi(serie, blocco=3, seme=42)
    ic2 = ic90_blocchi(serie, blocco=3, seme=42)
    assert ic1 == ic2, f"Determinismo fallito: {ic1} != {ic2}"
    print(f"✓ test_determinismo: {ic1} == {ic2}")


def test_serie_corta():
    """(b) Serie corta (<2 osservazioni) => ValueError chiaro, non crash."""
    try:
        ic90_blocchi([1.0], blocco=1)
        assert False, "Doveva sollevare ValueError per serie < 2 obs"
    except ValueError as e:
        assert "almeno 2 osservazioni" in str(e).lower()
        print(f"✓ test_serie_corta: ValueError corretto: {e}")
    
    try:
        ic90_blocchi([], blocco=1)
        assert False, "Doveva sollevare ValueError per serie vuota"
    except ValueError as e:
        assert "almeno 2 osservazioni" in str(e).lower()
        print(f"✓ test_serie_vuota: ValueError corretto: {e}")


def test_serie_costante():
    """(c) Serie costante => intervallo degenere gestito (ampiezza = 0)."""
    serie = [5.0, 5.0, 5.0, 5.0, 5.0]
    ic_inf, ic_sup = ic90_blocchi(serie, blocco=2, seme=123)
    # Per serie costante, tutte le medie bootstrap = 5.0, quindi IC = [5.0, 5.0]
    assert ic_inf == ic_sup == 5.0, f"Serie costante: IC degenere atteso [5,5], ottenuto ({ic_inf}, {ic_sup})"
    print(f"✓ test_serie_costante: IC degenere [{ic_inf}, {ic_sup}]")


def test_blocco_ge_serie():
    """(d) Blocco >= lunghezza serie => gestito (clamp dichiarato)."""
    serie = [1.0, 2.0, 3.0, 4.0, 5.0]
    # Blocco = lunghezza serie
    ic1 = ic90_blocchi(serie, blocco=5, seme=1)
    # Blocco > lunghezza serie
    ic2 = ic90_blocchi(serie, blocco=10, seme=1)
    # Devono dare stesso risultato (clamp a n)
    assert ic1 == ic2, f"Clamp fallito: blocco=5 -> {ic1}, blocco=10 -> {ic2}"
    print(f"✓ test_blocco_ge_serie: clamp funziona, IC = {ic1}")


def test_iid_serie():
    """(e) Su serie i.i.d. simulate (seed fisso) IC con blocco 1 è ragionevole."""
    import random
    random.seed(999)
    # Genera serie i.i.d. ~ N(0,1)
    serie = [random.gauss(0, 1) for _ in range(100)]
    ic_inf, ic_sup = ic90_blocchi(serie, blocco=1, seme=42, n_ricampiona=2000)
    ampiezza = ic_sup - ic_inf
    # Media vera = 0, IC 90% per n=100 dovrebbe avere ampiezza ~ 2*1.645/sqrt(100) ≈ 0.33
    # Accettiamo ampiezza in (0.05, 2.0) - non zero, non enorme
    assert ampiezza > 0.05, f"Ampiezza troppo piccola (quasi zero): {ampiezza}"
    assert ampiezza < 2.0, f"Ampiezza troppo grande: {ampiezza}"
    # L'IC dovrebbe contenere 0 (media vera) con alta probabilità
    assert ic_inf < 0 < ic_sup, f"IC [{ic_inf}, {ic_sup}] non contiene 0 (media vera)"
    print(f"✓ test_iid_serie: IC=[{ic_inf:.4f}, {ic_sup:.4f}], ampiezza={ampiezza:.4f}")


def test_sensibilita_ordine_lunghezze():
    """(f) sensibilita() ritorna TUTTE le lunghezze richieste, nell'ordine."""
    serie = list(range(20))  # 0..19
    blocchi_test = (5, 10, 15, 20)
    risultati = sensibilita(serie, blocchi=blocchi_test, seme=123, n_ricampiona=500)
    
    # Verifica che tutti i blocchi siano presenti
    assert len(risultati) == len(blocchi_test), f"Lunghezza risultati {len(risultati)} != {len(blocchi_test)}"
    
    # Verifica l'ordine
    for i, (r, b) in enumerate(zip(risultati, blocchi_test)):
        assert r['blocco'] == b, f"Ordine sbagliato posizione {i}: atteso blocco {b}, trovato {r['blocco']}"
        assert 'ic_inf' in r and 'ic_sup' in r and 'ampiezza' in r, f"Chiavi mancanti in risultato {i}"
        assert r['ampiezza'] == r['ic_sup'] - r['ic_inf'], f"Ampiezza non calcolata correttamente in posizione {i}"
    
    print(f"✓ test_sensibilita_ordine_lunghezze: {len(risultati)} risultati in ordine corretto")
    for r in risultati:
        print(f"  blocco={r['blocco']}, IC=[{r['ic_inf']:.4f}, {r['ic_sup']:.4f}], ampiezza={r['ampiezza']:.4f}")


def test_blocco_invalido():
    """Test extra: blocco < 1 deve sollevare ValueError."""
    serie = [1.0, 2.0, 3.0]
    try:
        ic90_blocchi(serie, blocco=0)
        assert False, "Doveva sollevare ValueError per blocco < 1"
    except ValueError as e:
        assert "blocco" in str(e).lower()
        print(f"✓ test_blocco_invalido: ValueError corretto: {e}")


def test_livello_personalizzato():
    """Test extra: livello di confidenza personalizzato."""
    serie = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    ic90 = ic90_blocchi(serie, blocco=2, livello=0.90, seme=1)
    ic95 = ic90_blocchi(serie, blocco=2, livello=0.95, seme=1)
    # IC 95% deve essere più largo di IC 90%
    amp90 = ic90[1] - ic90[0]
    amp95 = ic95[1] - ic95[0]
    assert amp95 >= amp90, f"IC 95% ({amp95}) non più largo di IC 90% ({amp90})"
    print(f"✓ test_livello_personalizzato: IC90 ampiezza={amp90:.4f}, IC95 ampiezza={amp95:.4f}")


def run_all_tests():
    """Esegue tutti i test e riporta risultati."""
    tests = [
        test_determinismo,
        test_serie_corta,
        test_serie_costante,
        test_blocco_ge_serie,
        test_iid_serie,
        test_sensibilita_ordine_lunghezze,
        test_blocco_invalido,
        test_livello_personalizzato,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"✗ {test.__name__} FALLITO: {e}")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} ERRORE: {type(e).__name__}: {e}")
    
    print(f"\n{'='*50}")
    print(f"RISULTATO: {passed} PASS, {failed} FAIL su {len(tests)} test")
    print(f"{'='*50}")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)