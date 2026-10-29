# Nesine iddaa bülteninden Süper Lig maç oranları -> data/nesine/<SEZON>/{guncel,gecmis}.csv
# Tek istek: www.nesine.com/iddaa sayfasının kullandığı açık bülten (cdnbulten.nesine.com). robots.txt: izinli.
# Pazar kodları: 1 = MS 1/X/2, 11/12/13 = Alt/Üst 1,5/2,5/3,5 (önce Alt, sonra Üst; modelle doğrulandı).
# 3 = Çifte şans (seçenek sırası doğrulanmadı, uygulamada gösterilmiyor). Karşılıklı gol büyük ihtimalle 38 (doğrulanmadı).
# Diğer tüm pazarlar ham olarak "ham" sütununda saklanır (kod|çizgi|oranlar).
import requests, pandas as pd, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor"))
import eslestir
SEZON = "2026-27"; OUT = f"data/nesine/{SEZON}"; os.makedirs(OUT, exist_ok=True)
URL = "https://cdnbulten.nesine.com/api/bulten/getprebultenfull"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) superlig-veri (kisisel analiz)", "Referer": "https://www.nesine.com/iddaa"}
TAKIMLAR = ["Alanyaspor", "Amedspor", "Besiktas", "Buyuksehyr", "Corum", "Erzurum BB", "Eyupspor", "Fenerbahce", "Galatasaray", "Gaziantep",
            "Genclerbirligi", "Goztep", "Kasimpasa", "Kocaelispor", "Konyaspor", "Rizespor", "Samsunspor", "Trabzonspor"]

r = requests.get(URL, headers=H, timeout=60)
if r.status_code != 200: sys.exit(f"Nesine bülteni alınamadı: HTTP {r.status_code}")
ea = r.json()["sg"]["EA"]
simdi = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
rows = []
for e in ea:
    if e.get("TYPE") != 1 or "HN" not in e: continue
    ev, dep = eslestir.takim(e["HN"], TAKIMLAR), eslestir.takim(e["AN"], TAKIMLAR)
    if not ev or not dep: continue                       # iki takım da Süper Lig takımı değilse (kupa vb. dahil) atla
    mk = {}
    for m in e.get("MA", []):
        mk.setdefault((m["MTID"], m.get("SOV", 0.0)), [o["O"] for o in m.get("OCA", [])])
    def g(k, i):   # Nesine kapalı seçeneği 1,00 olarak verir -> boş
        o = mk.get(k) or []
        return o[i] if len(o) > i and o[i] and o[i] > 1.0 else None
    d, ay, yil = e["D"].split(".")
    rows.append({"tarih": f"{yil}-{ay}-{d}", "saat": e["T"], "ev": ev, "dep": dep, "nesine_ev": e["HN"], "nesine_dep": e["AN"], "lig_kodu": e.get("LC"),
                 "ms1": g((1, 0.0), 0), "msx": g((1, 0.0), 1), "ms2": g((1, 0.0), 2),
                 "cs1x": g((3, 0.0), 0), "cs12": g((3, 0.0), 1), "csx2": g((3, 0.0), 2),
                 "alt15": g((11, 1.5), 0), "ust15": g((11, 1.5), 1), "alt25": g((12, 2.5), 0), "ust25": g((12, 2.5), 1), "alt35": g((13, 3.5), 0), "ust35": g((13, 3.5), 1),
                 "ham": json.dumps({f"{k[0]}|{k[1]}": v for k, v in mk.items()}, separators=(",", ":")), "cekildi": simdi})
G = pd.DataFrame(rows).sort_values(["tarih", "saat", "ev"]) if rows else pd.DataFrame()
G.to_csv(f"{OUT}/guncel.csv", index=False)
print("Süper Lig maçı:", len(G)); print(G[["tarih", "saat", "ev", "dep", "ms1", "msx", "ms2", "alt25", "ust25"]].to_string(index=False) if len(G) else "")

# geçmiş: ana oranlar değiştiyse yeni satır (açılıştan kapanışa oran hareketi)
ANA = ["ms1", "msx", "ms2", "alt25", "ust25"]; GP = f"{OUT}/gecmis.csv"
if len(G):
    yeni = G[["tarih", "saat", "ev", "dep"] + ANA + ["cekildi"]]
    if os.path.exists(GP):
        eski = pd.read_csv(GP); son = eski.sort_values("cekildi").groupby(["tarih", "ev", "dep"]).tail(1)
        m = yeni.merge(son[["tarih", "ev", "dep"] + ANA], on=["tarih", "ev", "dep"], how="left", suffixes=("", "_e"))
        def degisti(r):
            for c in ANA:
                a, b = r[c], r[c + "_e"]
                if pd.isna(a) != pd.isna(b) or (pd.notna(a) and abs(a - b) > 1e-9): return True
            return False
        yeni = m[m.apply(degisti, axis=1)][yeni.columns]; pd.concat([eski, yeni]).to_csv(GP, index=False)
    else:
        yeni.to_csv(GP, index=False)
    print("geçmişe eklenen satır:", len(yeni))
