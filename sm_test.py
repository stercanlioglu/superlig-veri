import os, sys, json, requests, datetime
T = os.environ.get("SPORTMONKS_TOKEN", "")
if not T: sys.exit("SPORTMONKS_TOKEN yok (Secrets'a eklenmemis)")
B = "https://api.sportmonks.com/v3"
def get(path, **p):
    p["api_token"] = T
    r = requests.get(B + path, params=p, timeout=60)
    print("->", path, r.status_code)
    try: return r.json()
    except Exception: print(r.text[:300]); return {}
# 1) Abonelikteki ligler
me = get("/my/leagues")
leagues = me.get("data", []) or []
print("ABONELIKTEKI LIGLER:", [(l.get("id"), l.get("name")) for l in leagues][:40])
tr = [l for l in leagues if "turk" in json.dumps(l, ensure_ascii=False).lower() or "super lig" in str(l.get("name", "")).lower() or "süper" in str(l.get("name", "")).lower()]
print("SUPER LIG ABONELIKTE MI:", bool(tr), tr[:2])
print("PLAN/BILGI:", json.dumps(me.get("subscription", me.get("meta", ""))[:1] if isinstance(me.get("subscription"), list) else me.get("subscription", ""), ensure_ascii=False)[:500])
# 2) Lig arama (abonelikte olmasa da kimligi gorelim)
s = get("/football/leagues/search/Super Lig")
print("ARAMA:", [(l.get("id"), l.get("name"), l.get("country_id")) for l in (s.get("data") or [])][:10])
# 3) Abonelikte Super Lig varsa son biten maci cek
if tr:
    lid = tr[0]["id"]
    end = datetime.date.today(); start = end - datetime.timedelta(days=21)
    f = get(f"/football/fixtures/between/{start}/{end}", include="lineups.details.type", filters=f"fixtureLeagues:{lid}")
    fx = f.get("data") or []
    print("MAC SAYISI:", len(fx))
    if fx:
        m = fx[0]; print("ORNEK MAC:", m.get("name"), m.get("starting_at"))
        ln = m.get("lineups") or []
        print("OYUNCU SAYISI:", len(ln))
        types = {}
        for p in ln:
            for d in p.get("details") or []:
                t = d.get("type") or {}; types[t.get("name") or d.get("type_id")] = (d.get("data") or {}).get("value")
        print("OYUNCU ISTATISTIK ALANLARI (ornek deger):", json.dumps(types, ensure_ascii=False, indent=1))
else:
    print("Super Lig aboneliginde degil: ucretsiz plan sadece sinirli ligleri kapsiyor olabilir.")
