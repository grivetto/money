"""money.esecuzione — il braccio che COSTRUISCE e (un giorno) invia gli ordini.

Regola fondante: il live non e' un flag che si dimentica di togliere, e' una
porta che si apre solo con tre chiavi insieme:

1. `MONEY_LIVE_ARMED=1` nell'ambiente (scelta esplicita del proprietario);
2. un file di promozione del cancello presente (l'edge esiste, misurato);
3. preflight passato (saldo, min_notional, simbolo, chiave).

Senza le tre, ogni ordine esce come DRY-RUN e non si muove un euro.
"""
