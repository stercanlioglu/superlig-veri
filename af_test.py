import os, sys, json, requests
T = os.environ.get("APIFOOTBALL_TOKEN", "")
if not T: sys.exit("APIFOOTBALL_TOKEN yok (Secrets'a eklenmemis)")
B = "https://v3.football.api-sports.io"
def get(path, **p):
    r = requests.get(B + path, headers={"x-apisports-key": T}, params=p, timeout=60)
    print("->", path, p, r.status_code, "kalan istek:", r.headers.get("x-ratelimit-requests-remaining"))
    try: j = r.json()
    except Exception: print(r.text[:300]); return {}
    if j.get("errors"): print("  HATA:", j["errors"])
    return j
acc = get("/status")
print("HESAP:", json.dumps((acc.get("response") or {}).get("subscription", ""), ensure_ascii=False), (acc.get("response") or {}).get("requests"))
L = get("/leagues", id=203)
resp = L.get("response") or []
if not resp: sys.exit("Super Lig (203) bulunamadi")
seasons = resp[0]["seasons"]
print("SEZONLAR (yil, oyuncu_istatistik, olaylar, kadro, istatistik):")
for s in seasons[-8:]:
    c = s.get("coverage", {}); f = c.get("fixtures", {})
    print(" ", s["year"], f.get("statistics_players"), f.get("events"), f.get("lineups"), f.get("statistics_fixtures"))
for y in (2026, 2025, 2024, 2023, 2022, 2021):
    F = get("/fixtures", league=203, season=y, status="FT")
    fx = F.get("response") or []
    print("SEZON", y, "bitmis mac:", len(fx))
    if fx:
        fid = fx[0]["fixture"]["id"]; print("ORNEK MAC:", fx[0]["teams"]["home"]["name"], "-", fx[0]["teams"]["away"]["name"], fid)
        P = get("/fixtures/players", fixture=fid)
        pr = P.get("response") or []
        if pr and pr[0].get("players"):
            st = pr[0]["players"][0]["statistics"][0]
            print("OYUNCU:", pr[0]["players"][0]["player"]["name"])
            print("ALANLAR:", json.dumps(st, ensure_ascii=False)[:1500])
            break
        else: print("  oyuncu istatistigi bos")
