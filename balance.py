import os, time, hmac, hashlib, requests
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
timestamp = int(time.time()*1000)
params = f"timestamp={timestamp}&recvWindow=5000"
signature = hmac.new(api_secret.encode(), params.encode(), hashlib.sha256).hexdigest()
headers = {"X-MBX-APIKEY": api_key}
url = f"https://api.binance.com/api/v3/account?{params}&signature={signature}"
r = requests.get(url, headers=headers, timeout=10)
if r.status_code == 200:
    data = r.json()
    eur = next((b for b in data["balances"] if b["asset"] == "EUR"), {"free":0,"locked":0})
    ada = next((b for b in data["balances"] if b["asset"] == "ADA"), {"free":0,"locked":0})
    print(f"EUR free: {eur[free]:.2f} EUR")
    print(f"EUR locked: {eur[locked]:.2f} EUR")
    print(f"ADA free: {ada[free]:.6f} ADA")
    print(f"ADA locked: {ada[locked]:.6f} ADA")
else:
    print(f"Account error: {r.status_code} {r.text}"
