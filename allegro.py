#!/usr/bin/env python3
"""
Allegro: automatyczna zmiana statusu zamówienia na "Odebrane" (PICKED_UP),
gdy przesyłka została dostarczona / odebrana przez kupującego.

Działanie:
 1. Pobiera zamówienia o statusie realizacji SENT (wysłane).
 2. Dla każdego pobiera przesyłki (numer listu + przewoźnik).
 3. Sprawdza tracking u przewoźnika przez API Allegro.
 4. Jeśli tracking pokazuje odbiór/dostarczenie -> ustawia PICKED_UP.

Wymagania: pip install requests
Konfiguracja: wpisz CLIENT_ID i CLIENT_SECRET aplikacji z
https://apps.developer.allegro.pl/ (typ aplikacji: "urządzenie" / device flow).
Pierwsze uruchomienie poprosi o autoryzację w przeglądarce.
"""
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
import requests
import re

# ---------------- KONFIGURACJA ----------------
CLIENT_ID = os.environ.get("ALLEGRO_CLIENT_ID", "96947bac30cf44ee92592572f470ab7a")
CLIENT_SECRET = os.environ.get("ALLEGRO_CLIENT_SECRET", "Ru95TI0exLMaIypXdrx9gCkqBkAS1mQYD10Xq4K0msM3P6yXOUUwdYTuSPSD9qxk")
SANDBOX = False          # True = allegro.pl.allegrosandbox.pl
DRY_RUN = False          # True = tylko loguje, nie zmienia statusów
TOKEN_FILE = "allegro_token.json"
POLL_INTERVAL_SEC = 0    # 0 = jedno uruchomienie (użyj z cronem); np. 3600 = pętla co godzinę

# Kody statusów trackingu uznawane za "odebrane".
# SPRAWDŹ w dokumentacji Allegro (GET /order/carriers/{carrierId}/tracking)
# i dopasuj do swoich przewoźników.
DELIVERED_CODES = {"DELIVERED", "PICKED_UP"}
# Kody trackingu oznaczające, że paczka jest już w drodze (przewoźnik ją odebrał).
# SPRAWDŹ w logu, jakie kody faktycznie zwracają Twoi przewoźnicy, i dopasuj.
IN_TRANSIT_CODES = {"IN_TRANSIT", "RELEASED_FOR_DELIVERY", "OUT_FOR_DELIVERY"}
# Kody trackingu oznaczające, że paczka czeka na odbiór ("Odbierz paczkę" / do odbioru).
READY_FOR_PICKUP_CODES = {"AVAILABLE_FOR_PICKUP", "NOTICE_LEFT", "READY_FOR_PICKUP"}
# Dodatkowo: fragmenty opisu statusu (małymi literami), które też oznaczają "do odbioru".
READY_FOR_PICKUP_KEYWORDS = ["odbierz", "do odbioru", "gotowa do odbioru", "awizo"]
 
PRE_SENT_STATUSES = ["NEW", "PROCESSING", "READY_FOR_SHIPMENT"]
 

 
# Polskie nazwy statusów zamówienia jak w Allegro (tylko do wyświetlania).
STATUS_PL = {
    "NEW": "NOWE",
    "PROCESSING": "W REALIZACJI",
    "SUSPENDED": "WSTRZYMANE",
    "READY_FOR_SHIPMENT": "DO WYSŁANIA",
    "READY_FOR_PICKUP": "DO ODBIORU",
    "SENT": "WYSŁANE",
    "PICKED_UP": "ODEBRANE",
    "CANCELLED": "ANULOWANE",
}
 
# -----------------------------------------------
 
AUTH_HOST = "allegro.pl.allegrosandbox.pl" if SANDBOX else "allegro.pl"
API_HOST = "api.allegro.pl.allegrosandbox.pl" if SANDBOX else "api.allegro.pl"
API = f"https://{API_HOST}"
MIME = "application/vnd.allegro.public.v1+json"
SCOPES = "allegro:api:orders:read allegro:api:orders:write allegro:api:shipments:read"
 
 
def _basic():
    raw = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
 
 
def _save(tok):
    tok["obtained_at"] = time.time()
    with open(TOKEN_FILE, "w") as f:
        json.dump(tok, f)
 
 
def device_flow():
    r = requests.post(
        f"https://{AUTH_HOST}/auth/oauth/device",
        headers={**_basic(), "Content-Type": "application/x-www-form-urlencoded"},
        data={"client_id": CLIENT_ID, "scope": SCOPES},
    )
    r.raise_for_status()
    d = r.json()
    print(f"\nOtwórz: {d['verification_uri_complete']}\nI zatwierdź dostęp.\n")
    interval = d.get("interval", 5)
    deadline = time.time() + d.get("expires_in", 600)
    while time.time() < deadline:
        time.sleep(interval)
        t = requests.post(
            f"https://{AUTH_HOST}/auth/oauth/token",
            headers=_basic(),
            params={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": d["device_code"],
            },
        )
        if t.status_code == 200:
            tok = t.json()
            _save(tok)
            return tok
        err = t.json().get("error")
        if err == "slow_down":
            interval += 5
        elif err != "authorization_pending":
            sys.exit(f"Błąd autoryzacji: {t.text}")
    sys.exit("Czas na autoryzację minął.")
 
 
def refresh(tok):
    r = requests.post(
        f"https://{AUTH_HOST}/auth/oauth/token",
        headers=_basic(),
        params={
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "redirect_uri": "http://localhost",
        },
    )
    if r.status_code != 200:
        print("Nie udało się odświeżyć tokenu, wymagana ponowna autoryzacja.")
        return device_flow()
    new = r.json()
    _save(new)
    return new
 
 
def get_token():
    if not os.path.exists(TOKEN_FILE):
        return device_flow()["access_token"]
    with open(TOKEN_FILE) as f:
        tok = json.load(f)
    # odśwież z zapasem 5 min
    if time.time() > tok["obtained_at"] + tok.get("expires_in", 43200) - 300:
        tok = refresh(tok)
    return tok["access_token"]
 
 
def api(method, path, **kw):
    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Accept": MIME,
        "Content-Type": MIME,
    }
    for attempt in range(3):
        r = requests.request(method, API + path, headers=headers, timeout=30, **kw)
        if r.status_code == 429:  # rate limit
            time.sleep(int(r.headers.get("Retry-After", 5)))
            continue
        return r
    return r
 
 
def orders_with_status(status):
    offset, limit = 0, 100
    while True:
        r = api("GET", "/order/checkout-forms", params={
            "fulfillment.status": status,
            "limit": limit,
            "offset": offset,
        })
        r.raise_for_status()
        forms = r.json().get("checkoutForms", [])
        yield from forms
        if len(forms) < limit:
            return
        offset += limit
 
 
def shipments_of(order_id):
    r = api("GET", f"/order/checkout-forms/{order_id}/shipments")
    if r.status_code != 200:
        print(f"  ! shipments {order_id}: {r.status_code} {r.text[:200]}")
        return []
    return r.json().get("shipments", [])
 
 
def tracking_codes(carrier_id, waybill):
    r = api("GET", f"/order/carriers/{carrier_id}/tracking", params={"waybill": waybill})
    if r.status_code != 200:
        print(f"  ! tracking {waybill}: {r.status_code} {r.text[:200]}")
        return set()
    data = r.json() or {}
    codes = set()
    # odpowiedź może zawierać listę przesyłek z listą statusów – zbieramy wszystkie kody
    for item in (data.get("waybills") or [data]):
        item = item or {}
        details = item.get("trackingDetails") or {}
        statuses = details.get("statuses") or item.get("statuses") or []
        for st in statuses:
            if st.get("code"):
                codes.add(st["code"])
                # zapamiętujemy też godzinę tego statusu
                if st.get("occurredAt"):
                    codes.add(f"TS:{st['code']}|{st['occurredAt']}")
            if st.get("description"):
                codes.add("DESC:" + st["description"].lower())
    return codes
 
 
def set_status(order_id, status):
    pl = STATUS_PL.get(status, status)
    if DRY_RUN:
        print(f"  [DRY_RUN] ustawiłbym {pl} dla {order_id}")
        return
    r = api("PUT", f"/order/checkout-forms/{order_id}/fulfillment",
            json={"status": status})
    if r.status_code in (200, 204):
        print(f"  Zmieniono | {order_id} -> {pl}")
    else:
        print(f"  ! zmiana statusu {order_id}: {r.status_code} {r.text[:300]}")
 
 
def collect_codes(shipments, oid):
    """Zwraca listę zbiorów kodów trackingu (po jednym na przesyłkę) albo None, jeśli brak danych."""
    result = []
    for s in shipments:
        carrier, waybill = s.get("carrierId"), s.get("waybill")
        if not carrier or not waybill:
            return None
        result.append(tracking_codes(carrier, waybill))
    return result
 
 
RANK = {"NEW": 0, "PROCESSING": 1, "READY_FOR_SHIPMENT": 2,
        "SENT": 3, "READY_FOR_PICKUP": 4, "PICKED_UP": 5}
 
 
def is_ready_for_pickup(codes):
    if codes & READY_FOR_PICKUP_CODES:
        return True
    return any(c.startswith("DESC:") and any(k in c for k in READY_FOR_PICKUP_KEYWORDS)
               for c in codes)
 
 
def classify(all_codes):
    """Zwraca docelowy status zamówienia na podstawie trackingu wszystkich paczek."""
    if all(c & DELIVERED_CODES for c in all_codes):
        return "PICKED_UP"
    if any(is_ready_for_pickup(c) for c in all_codes):
        return "READY_FOR_PICKUP"
    if any(c & (IN_TRANSIT_CODES | DELIVERED_CODES) for c in all_codes):
        return "SENT"
    return None
 
def waiting_in_locker(all_codes):
    """Zwraca, od jak dawna paczka czeka na odbiór (timedelta) albo None."""
    times = []
    for codes in all_codes:
        for c in codes:
            if c.startswith("TS:"):
                code, _, ts = c[3:].partition("|")
                if code in READY_FOR_PICKUP_CODES:
                    try:
                        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone.utc)
                    times.append(t)
    if not times:
        return None
    return datetime.now(timezone.utc) - min(times)
 
CARRIER_RULES = [
    (r"\bdpd\b", "DPD"),
    (r"\bups\b", "UPS"),
    (r"\bdhl\b", "DHL"),
    (r"orlen", "Orlen"),
    (r"inpost|paczkomat", "InPost"),
    (r"\bgls\b", "GLS"),
    (r"fedex", "FedEx"),
    (r"poczt", "Poczta"),
    (r"\bone\b", "One"),   # na końcu: zostaje tylko, gdy nie ma innego kuriera
]


def carrier_label(form, shipments):
    """Nazwa kuriera na podstawie metody dostawy zamówienia."""
    method = ((form.get("delivery") or {}).get("method") or {}).get("name") or ""
    low = method.lower()
    for pattern, label in CARRIER_RULES:
        if re.search(pattern, low):
            return label
    # nie rozpoznano: pokaż techniczny identyfikator przewoźnika
    ids = sorted({str(s.get("carrierId") or "?").title() for s in shipments})
    return ", ".join(ids) or "-"
 
def run_once():
    from collections import Counter
    counts = Counter()      # zamówienia wg statusu
    at_me = Counter()       # zamówienia jeszcze nie wysłane, wg kuriera
    checked = changed = 0
    for current in PRE_SENT_STATUSES + ["SENT", "READY_FOR_PICKUP"]:
        for form in orders_with_status(current):
            oid = form["id"]
            checked += 1
            counts[current] += 1
            shipments = shipments_of(oid)
            label = carrier_label(form, shipments)
            tag = f"{label:<7}"
            eff = current  # status po ewentualnej zmianie

            all_codes = collect_codes(shipments, oid) if shipments else None
            if not all_codes:
                # brak listu przewozowego albo danych trackingu: pokazujemy, żeby liczba się zgadzała
                print(f"{oid} | {tag} (brak danych trackingu) | {STATUS_PL.get(current, current)}")
            else:
                target = classify(all_codes)
                waybills = ", ".join(str(s.get("waybill")) for s in shipments)
                line = f"{oid} | {tag} {waybills} | {STATUS_PL.get(current, current)}"

                # zmieniamy tylko "do przodu", nigdy wstecz
                will_change = bool(target and RANK[target] > RANK[current])
                if will_change:
                    line += f"  ->  {STATUS_PL.get(target, target)}"

                # ile paczka leży w automacie
                if target == "READY_FOR_PICKUP":
                    w = waiting_in_locker(all_codes)
                    if w is not None:
                        days = w.days
                        hours = w.seconds // 3600
                        txt = f"{days} dni {hours} godz." if days else f"{hours} godz."
                        line += f"  |  w automacie: {txt}"
                        if days >= 3:
                            line += "  !!!"

                print(line)

                if will_change:
                    set_status(oid, target)
                    changed += 1
                    counts[current] -= 1
                    counts[target] += 1
                    eff = target

            if eff in PRE_SENT_STATUSES:
                at_me[label] += 1

    print(f"\nSprawdzono: {checked}, do zmiany/zmieniono: {changed}")
    order = ["NEW", "PROCESSING", "READY_FOR_SHIPMENT", "READY_FOR_PICKUP", "SENT", "PICKED_UP"]
    summary = " | ".join(f"{STATUS_PL[s]}: {counts[s]}" for s in order if counts[s])
    print(f"Podsumowanie: {summary} | Razem: {sum(counts.values())}")
    if at_me:
        print("Jeszcze nie wysłane: " +
              " | ".join(f"{n}: {c}" for n, c in at_me.most_common()))

 
if __name__ == "__main__":
    if POLL_INTERVAL_SEC:
        while True:
            run_once()
            time.sleep(POLL_INTERVAL_SEC)
    else:
        run_once()