# FotMob Süper Lig sezon istatistikleri -> data/fotmob/<SEZON>/{takim,oyuncu,istatistikler}.csv
# Lig istatistik sayfası (robots.txt: izinli) her istatistiğin tam listesine bağlantı veriyor (data.fotmob.com/stats/...json);
# sadece bu bağlantılar okunur, /api/ kullanılmaz. Yavaş çekilir (istek arası 3 sn, ~70 istek).
import requests, pandas as pd, re, json, time, os, sys
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) superlig-veri (kisisel analiz, yavas)", "Accept-Language": "en"}
SAYFA = "https://www.fotmob.com/leagues/71/stats/super-lig"
BEKLE = 3

def get(url, json_=False):
    for k in range(3):
        try:
            r = requests.get(url, headers=H, timeout=40)
            if r.status_code == 200: return r.json() if json_ else r.text
            print("  HTTP", r.status_code, url)
        except Exception as e:
            print("  hata", type(e).__name__, url)
        time.sleep(10 * (k + 1))
    return None

html = get(SAYFA)
if not html: sys.exit("FotMob lig sayfası alınamadı")
pp = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))["props"]["pageProps"]
ad = pp["stats"]["seasonStatLinks"][0]["Name"]               # "2026/2027"
SEZON = f"{ad[:4]}-{ad[-2:]}"; OUT = f"data/fotmob/{SEZON}"; os.makedirs(OUT, exist_ok=True)

tablo = {"takim": {}, "oyuncu": {}}; sozluk = []
for tur, liste in (("oyuncu", pp["stats"]["players"]), ("takim", pp["stats"]["teams"])):
    for s in liste:
        time.sleep(BEKLE)
        d = get(s["fetchAllUrl"], json_=True)
        if not d: continue
        t = d["TopLists"][0]; st = t["StatName"]
        sozluk.append({"tur": tur, "stat": st, "baslik": t["Title"], "alt_baslik": t.get("Subtitle"), "kategori": t.get("Category")})
        for r in t["StatList"]:
            if tur == "takim":
                k = r["TeamId"]; row = tablo["takim"].setdefault(k, {"takim_id": k, "takim": r["ParticipantName"]})
            else:
                k = r["ParticiantId"]; row = tablo["oyuncu"].setdefault(k, {"oyuncu_id": k, "oyuncu": r["ParticipantName"], "takim_id": r["TeamId"],
                                                                            "takim": r.get("TeamName"), "pozisyon": (r.get("Positions") or [None])[0]})
                row["dakika"] = max(row.get("dakika", 0), r.get("MinutesPlayed") or 0)
            row["mac"] = max(row.get("mac", 0), r.get("MatchesPlayed") or 0)
            row[st] = r["StatValue"]
            if r.get("SubStatValue") is not None: row[f"{st}__alt"] = r["SubStatValue"]
        print(f"{tur:6s} {st:45s} {len(t['StatList'])}")

for tur, rows in tablo.items():
    df = pd.DataFrame(list(rows.values()))
    df.to_csv(f"{OUT}/{tur}.csv", index=False); print(tur, df.shape)
pd.DataFrame(sozluk).to_csv(f"{OUT}/istatistikler.csv", index=False)
json.dump({"sezon": SEZON, "cekildi": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}, open(f"{OUT}/bilgi.json", "w"))
