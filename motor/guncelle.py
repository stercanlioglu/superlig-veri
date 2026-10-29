# Uygulama verisini depodaki güncel veriden yeniden üretir ve index.html'i yeniden şifreler.
# Girdi: data/fd/T1_*.csv (sonuç+oran+şut), data/temiz/<SEZON>/ (TFF oyuncu/maç), index.html (şifreli uygulama).
# Kullanım (depo kökünde): SL_KULLANICI=... SL_SIFRE=... python motor/guncelle.py
# Değişmeyen bölümler (market, extra, live.ak, Tahmin Ligi) mevcut sayfadan aynen korunur.
import os, sys, re, json, glob, math
from datetime import datetime
import numpy as np, pandas as pd
from scipy.stats import poisson
K = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(K)
sys.path.insert(0, K); sys.path.insert(0, ROOT)
from superlig import Elo, elo_to_probs, dc_predict, dc_tau, logloss, rps, brier
from dcr import dc_fit, power_devig
import sifrele

SEZON = "2026-27"; XG_C = 0.3113385587093833          # xG vekili = XG_C × isabetli şut
FD_AD = {"Erzurumspor": "Erzurum BB"}                   # football-data -> model takım adı
TM = {"AMED SPORTİF FAALİYETLER": "Amedspor", "ARCA ÇORUM FK": "Corum", "BEŞİKTAŞ A.Ş.": "Besiktas", "CORENDON ALANYASPOR": "Alanyaspor",
      "ERZURUMSPOR FK": "Erzurum BB", "EYÜPSPOR": "Eyupspor", "FENERBAHÇE A.Ş.": "Fenerbahce", "GALATASARAY A.Ş.": "Galatasaray",
      "GAZİANTEP FUTBOL KULÜBÜ A.Ş.": "Gaziantep", "GENÇLERBİRLİĞİ": "Genclerbirligi", "GÖZTEPE A.Ş.": "Goztep", "KASIMPAŞA A.Ş.": "Kasimpasa",
      "KOCAELİSPOR": "Kocaelispor", "SAMSUNSPOR A.Ş.": "Samsunspor", "TRABZONSPOR A.Ş.": "Trabzonspor", "TÜMOSAN KONYASPOR": "Konyaspor",
      "ÇAYKUR RİZESPOR A.Ş.": "Rizespor", "İSTANBUL BAŞAKŞEHİR FK": "Buyuksehyr"}   # TFF -> model takım adı
AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
ODDS = ["B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA", "AvgCH", "AvgCD", "AvgCA", "PSCH", "PSCD", "PSCA"]
CACHE = f"{ROOT}/data/model/tahminler.csv"
if not (os.environ.get("SL_KULLANICI") and os.environ.get("SL_SIFRE")):
    sys.exit("SL_KULLANICI / SL_SIFRE tanımlı değil (GitHub: Settings → Secrets and variables → Actions)")

# ---------- 1. veri: football-data ----------
fd = []
for f in sorted(glob.glob(f"{ROOT}/data/fd/T1_*.csv")):
    d = pd.read_csv(f, encoding="utf-8-sig").dropna(subset=["FTHG", "FTAG"])
    d.insert(0, "season", re.search(r"T1_(\d{4}-\d{2})", f).group(1)); fd.append(d)
fd = pd.concat(fd, ignore_index=True).copy()
fd["HomeTeam"] = fd.HomeTeam.replace(FD_AD); fd["AwayTeam"] = fd.AwayTeam.replace(FD_AD)
fd["date"] = pd.to_datetime(fd.Date, dayfirst=True)
for c in ODDS:
    if c not in fd: fd[c] = np.nan
df = pd.DataFrame({"season": fd.season, "date": fd.date, "home": fd.HomeTeam.str.strip(), "away": fd.AwayTeam.str.strip(),
                   "hg": fd.FTHG.astype(int), "ag": fd.FTAG.astype(int)}).sort_values("date", kind="stable").reset_index(drop=True)
df["res"] = np.sign(df.hg - df.ag)
odds = {(r[0], r[1], r[2]): dict(zip(ODDS, r[3:])) for r in fd[["season", "HomeTeam", "AwayTeam"] + ODDS].itertuples(index=False)}
print("maç:", len(df), df.date.max().date())

# ---------- 2. ileri yürüyen tahminler (önbellekli: eski maçların tahmini değişmez, sadece yeniler hesaplanır) ----------
key = lambda s, d, h, a: f"{s}|{pd.Timestamp(d).date()}|{h}|{a}"
cache = {}
if os.path.exists(CACHE):
    for r in pd.read_csv(CACHE).itertuples(index=False): cache[r.key] = r
elo = Elo(); model = None; last = None; seen = set(); first = df.season.min(); rows = []; yeni = 0
for i, r in df.iterrows():
    for t in (r.home, r.away):
        if t not in seen and r.season != first: elo.r.setdefault(t, 1440)
        seen.add(t); elo.new_season(t, r.season)
    if i > 150:
        k = key(r.season, r.date, r.home, r.away); c = cache.get(k)
        if c is not None:
            p, pe, pdc = np.array([c.p_h, c.p_d, c.p_a]), np.array([c.pe_h, c.pe_d, c.pe_a]), np.array([c.pdc_h, c.pdc_d, c.pdc_a])
            lh, la, has = c.lh, c.la, bool(c.has_dc)
        else:
            if model is None or (r.date - last).days >= 7:
                tr = df.iloc[:i]; tr = tr[tr.date >= r.date - pd.Timedelta(days=900)]; model = dc_fit(tr, r.date); last = r.date
            pe = elo_to_probs(elo.expect(r.home, r.away)); dc = dc_predict(model, r.home, r.away)
            p = 0.5 * pe + 0.5 * dc["p"] if dc else pe; pdc = dc["p"] if dc else pe
            lh, la, has = (dc["lh"], dc["la"], True) if dc else (np.nan, np.nan, False); yeni += 1
        rows.append({"key": k, "season": r.season, "date": r.date, "home": r.home, "away": r.away, "hg": r.hg, "ag": r.ag, "res": r.res,
                     "p": p, "pe": pe, "pdc": pdc, "lh": lh, "la": la, "has_dc": has, **(odds.get((r.season, r.home, r.away)) or {})})
    elo.update(r.home, r.away, r.hg, r.ag)
P = pd.DataFrame(rows)
os.makedirs(os.path.dirname(CACHE), exist_ok=True)
pd.DataFrame({"key": P.key, **{f"{n}_{s}": P[n].map(lambda v, j=j: float(v[j])) for n in ("p", "pe", "pdc") for j, s in enumerate("hda")},
              "lh": P.lh, "la": P.la, "has_dc": P.has_dc.astype(int)}).to_csv(CACHE, index=False, float_format="%.12g")  # sabit biçim: tekrar yazınca değişmesin
print("tahmin:", len(P), "yeni hesaplanan:", yeni)

# ---------- 3. mevcut uygulamayı çöz ----------
USER, PW = os.environ["SL_KULLANICI"], os.environ["SL_SIFRE"]
eski_sayfa = open(f"{ROOT}/index.html", encoding="utf-8").read()
H = sifrele.coz(eski_sayfa, USER, PW)
RX = r'(<script id="data" type="application/json">)(.*?)(</script>)'
J = json.loads(re.search(RX, H, re.S).group(2))

# ---------- 4. takım tablosu, lig profili, model metrikleri (build2) ----------
ref = df.date.max() + pd.Timedelta(days=1); model = dc_fit(df[df.date >= ref - pd.Timedelta(days=900)], ref)
cur = df[df.season == SEZON]; T = []
for t in sorted(set(cur.home) | set(cur.away)):
    g = cur[(cur.home == t) | (cur.away == t)]
    pts = sum(3 if (x.home == t and x.hg > x.ag) or (x.away == t and x.ag > x.hg) else 1 if x.hg == x.ag else 0 for x in g.itertuples())
    gf = sum(x.hg if x.home == t else x.ag for x in g.itertuples()); ga = sum(x.ag if x.home == t else x.hg for x in g.itertuples())
    T.append({"name": t, "elo": round(elo.r[t]), "att": round(float(model["att"][t]), 2), "def": round(float(model["def"][t]), 2), "last": f"{pts} p · {int(gf)}-{int(ga)}"})
T.sort(key=lambda x: -x["elo"]); J["teams"] = T; J["ha"] = round(float(model["ha"]), 3); J["rho"] = round(float(model["rho"]), 3)

# kaç hafta oynandı: en çok maç oynayan takımın maç sayısı (her takım haftada bir maç)
M = pd.read_csv(f"{ROOT}/data/temiz/{SEZON}/maclar.csv")
HAFTA = int(pd.concat([cur.home, cur.away]).value_counts().max())
son = cur.date.max(); TARIH = f"{son.day} {AY[son.month - 1]} {son.year}"
gecmis = sorted(s for s in df.season.unique() if s != SEZON)
J["league"] = {"matches": len(df), "span": f"{gecmis[0]} → {gecmis[-1]} (tam sezonlar), {SEZON} ilk {HAFTA} hafta",
               "home": round(float((df.res == 1).mean()), 3), "draw": round(float((df.res == 0).mean()), 3), "away": round(float((df.res == -1).mean()), 3),
               "hg": round(float(df.hg.mean()), 2), "ag": round(float(df.ag.mean()), 2)}

P["res"] = P.res.astype(int); Pt = P[P.season >= "2022-23"].copy()
cum = np.zeros(3); base = []
for r in df.itertuples():
    base.append(cum.copy() / cum.sum() if cum.sum() > 0 else np.array([.45, .27, .28]))
    cum += {1: [1, 0, 0], 0: [0, 1, 0], -1: [0, 0, 1]}[int(r.res)]
Pt["p_base"] = [base[151 + i] for i in Pt.index]; Pt["p_unif"] = [np.array([1 / 3] * 3)] * len(Pt)
acc = lambda ps, rs: float(np.mean([[1, 0, -1][int(np.argmax(p))] == r for p, r in zip(ps, rs)]))
J["metrics"] = {k: {"logloss": float(np.mean([logloss(p, r) for p, r in zip(Pt[c], Pt.res)])), "rps": float(np.mean([rps(p, r) for p, r in zip(Pt[c], Pt.res)])),
                    "brier": float(np.mean([brier(p, r) for p, r in zip(Pt[c], Pt.res)])), "acc": acc(Pt[c], Pt.res)}
                for k, c in (("unif", "p_unif"), ("base", "p_base"), ("elo", "pe"), ("dc", "pdc"), ("ens", "p"))}
Pt["ph"] = Pt.p.apply(lambda p: p[0]); Pt["win"] = (Pt.res == 1).astype(int); Pt["bin"] = pd.cut(Pt.ph, [0, .3, .4, .5, .6, .7, 1])
J["cal"] = [{"bin": str(b), "n": int(len(g)), "pred": round(float(g.ph.mean()), 3), "real": round(float(g.win.mean()), 3)} for b, g in Pt.groupby("bin", observed=True)]
J["seasons"] = {s: {"n": int(len(g)), "logloss": round(float(np.mean([logloss(p, r) for p, r in zip(g.p, g.res)])), 3),
                    "rps": round(float(np.mean([rps(p, r) for p, r in zip(g.p, g.res)])), 3), "acc": round(acc(g.p, g.res), 3)} for s, g in Pt.groupby("season")}
J["metrics_n"] = int(len(Pt))

# canlı test (model vs açılış ortalama oranı); "ak" örneği sabit kalır
L = P[P.season == SEZON].dropna(subset=["AvgH"]).copy(); L["pm"] = L.apply(lambda r: np.array(power_devig([r.AvgH, r.AvgD, r.AvgA])), axis=1)
lt = {"n": int(len(L))}
for k in ("p", "pm"):
    lt[k] = {"logloss": round(float(np.mean([logloss(p, r) for p, r in zip(L[k], L.res)])), 4), "rps": round(float(np.mean([rps(p, r) for p, r in zip(L[k], L.res)])), 4),
             "brier": round(float(np.mean([brier(p, r) for p, r in zip(L[k], L.res)])), 4), "acc": round(acc(L[k], L.res), 4)}
J["live"]["test"] = lt
J["live"]["rows"] = [{"date": r.date.date().isoformat(), "home": r.home, "away": r.away, "hg": int(r.hg), "ag": int(r.ag), "res": int(r.res), "has_dc": bool(r.has_dc),
                      "odds": [float(r.AvgH), float(r.AvgD), float(r.AvgA)], "p": [round(float(x), 3) for x in r.p], "pm": [round(float(x), 3) for x in r.pm]} for r in L.itertuples()]

# ---------- 5. xG: football-data gerçek xG (HxG/AxG) varsa o, yoksa isabetli şut vekili ----------
c = fd[fd.season == SEZON].copy()
gercek = "HxG" in c and c.HxG.notna().all() and "AxG" in c and c.AxG.notna().all()
if gercek: c["hx"], c["ax"] = c.HxG, c.AxG
else: c["hx"], c["ax"] = XG_C * c.HST, XG_C * c.AST
J["xg"] = {"xg_total": round(float(c.hx.sum() + c.ax.sum()), 1), "goals_total": int(c.FTHG.sum() + c.FTAG.sum()),
           "r_diff": round(float(np.corrcoef(c.hx - c.ax, c.FTHG - c.FTAG)[0, 1]), 2), "n": int(len(c)), "c": [XG_C, 0.0],
           "src": "gercek" if gercek else "vekil"}
xt = []
for t in sorted(set(c.HomeTeam)):
    h, a = c[c.HomeTeam == t], c[c.AwayTeam == t]; m = len(h) + len(a)
    xt.append({"team": t, "m": m, "xg": float((h.hx.sum() + a.ax.sum()) / m), "xga": float((h.ax.sum() + a.hx.sum()) / m), "g": float((h.FTHG.sum() + a.FTAG.sum()) / m)})
J["xg_teams"] = sorted(xt, key=lambda x: -(x["xg"] - x["xga"]))

# ---------- 6. Takımlar/Oyuncular sayfa verisi (build_pages) ----------
def n(v): return None if pd.isna(v) else (int(v) if float(v) == int(v) else float(v))
f2 = fd.sort_values("date", kind="stable")
mcols = ["FTHG", "FTAG", "HTHG", "HTAG", "HS", "AS", "HST", "AST", "HC", "AC", "HY", "AY", "HR", "AR", "HF", "AF"]
matches = [[r.season, r.date.strftime("%Y-%m-%d"), r.HomeTeam, r.AwayTeam] + [n(getattr(r, x)) for x in mcols] for r in f2.itertuples()]
OM = pd.read_csv(f"{ROOT}/data/temiz/{SEZON}/oyuncu_mac.csv")
eksik = sorted(set(OM.takim) - set(TM)) + sorted(set(M.ev) - set(TM))
if eksik: sys.exit(f"TM sözlüğünde olmayan TFF takım adı: {eksik}")
OM["takim"] = OM.takim.map(TM); M["ev"] = M.ev.map(TM); M["dep"] = M.dep.map(TM)
tm = {}
for r in M.sort_values("tarih").itertuples():
    tm.setdefault(r.ev, []).append(r.macId); tm.setdefault(r.dep, []).append(r.macId)
def tcase(s):
    tr = any(ch in s for ch in "İĞŞ"); out = []
    for w in s.split():
        w = w.replace("İ", "i").replace("I", "ı").lower() if tr else w.lower()
        out.append((w[:1].replace("i", "İ").upper() if tr else w[:1].upper()) + w[1:])
    return " ".join(out)
pr = []
for pid, d in OM.groupby("kisiId"):
    team = d.sort_values("tarih").takim.iloc[-1]; dt = d[d.takim == team]; mm = tm[team]; ids = set(dt.macId)
    pr.append(dict(id=int(pid), ad=tcase(d.oyuncu.iloc[0].replace("  ", " ")), takim=team, mac=dt.macId.nunique(), ilk11=int(dt.ilk11.sum()), dk=int(dt.dk.sum()),
                   gol=int(dt.gol.sum()), pen=int(dt.penalti.sum()), kafa=int(dt.kafa.sum()), sari=int(dt.sari.sum()), cift=int(dt.cift.sum()), kirmizi=int(dt.kirmizi.sum()),
                   son=[int(dt[dt.macId == m].dk.sum()) if m in ids else 0 for m in mm[-5:]]))
R = pd.DataFrame(pr); R["tmac"] = R.takim.map({t: len(v) for t, v in tm.items()})
R["npg"] = R.gol - R.pen; R["m90"] = R.dk / 90; prior = R.npg.sum() / R.m90.sum(); k = 3.0
R["npg90"] = (R.npg + prior * k) / (R.m90 + k); R["sure"] = (R.dk / (R.tmac * 90)).clip(0, 1)
R["kart90"] = (R.sari + 2 * R.cift + 3 * R.kirmizi) / R.m90.clip(lower=1)
el = R.dk >= 180
pct = lambda s: s[el].rank(pct=True).reindex(s.index).fillna(0)
R["puan"] = (60 * pct(R.npg90) + 30 * pct(R.sure) - 10 * pct(R.kart90) + 10).round(0).clip(0, 100); R.loc[~el, "puan"] = None
R = R.sort_values(["puan", "dk"], ascending=False, na_position="last")

# FotMob (fotmob.py çıktısı varsa): oyuncuya xG/xA/not, takıma topa sahip olma/kadro değeri/büyük fırsat
FMD = f"{ROOT}/data/fotmob/{SEZON}"; fmo = {}; J.pop("fm", None)
if os.path.exists(f"{FMD}/oyuncu.csv"):
    import eslestir
    FO, FT = pd.read_csv(f"{FMD}/oyuncu.csv"), pd.read_csv(f"{FMD}/takim.csv")
    adlar = [t["name"] for t in T]; idm = {r.takim_id: eslestir.takim(r.takim, adlar) for r in FT.itertuples()}
    es = eslestir.oyuncular([(r.oyuncu_id, r.oyuncu, idm.get(r.takim_id), r.dakika) for r in FO.itertuples()],
                            [(r.id, r.ad, r.takim, r.dk) for r in R.itertuples()])
    fr = FO.set_index("oyuncu_id"); v = lambda x: None if pd.isna(x) else float(x)
    fmo = {tk: (v(fr.at[fk, "expected_goals"]), v(fr.at[fk, "expected_assists"]), v(fr.at[fk, "rating"])) for tk, fk in es.items()}
    J["fm"] = {"tarih": json.load(open(f"{FMD}/bilgi.json"))["cekildi"],
               "teams": {idm[r.takim_id]: {"xg": v(r.expected_goals_team), "xga": v(r.expected_goals_conceded_team), "pos": v(r.possession_percentage_team),
                                           "val": v(r.squad_value_team), "rt": v(r.rating_team), "bc": v(r.big_chance_team)} for r in FT.itertuples() if idm.get(r.takim_id)}}
    print("FotMob eşleşen oyuncu:", len(es), "/", len(R))
J["pg"] = {"matches": matches, "pcols": ["id", "ad", "takim", "mac", "ilk11", "dk", "gol", "pen", "kafa", "sari", "cift", "kirmizi", "son", "puan", "sure", "xg", "xa", "rt"],
           "players": [[r.id, r.ad, r.takim, r.mac, r.ilk11, r.dk, r.gol, r.pen, r.kafa, r.sari, r.cift, r.kirmizi, r.son,
                        None if pd.isna(r.puan) else int(r.puan), round(float(r.sure), 2), *fmo.get(r.id, (None, None, None))] for r in R.itertuples()],
           "tm_n": {t: len(v) for t, v in tm.items()}, "prior": round(float(prior), 3)}

# ---------- 7. sayfaya yaz: veri + metindeki hafta/tarih ifadeleri ----------
veri = json.dumps(J, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
Y = re.sub(RX, lambda m: m.group(1) + veri + m.group(3), H, count=1, flags=re.S)
nS = len(cur)
for pat, rep in [(r"\d+ \S+ 20\d\d itibarıyla güncel \(\d+\. hafta dahil\)", f"{TARIH} itibarıyla güncel ({HAFTA}. hafta dahil)"),
                 (rf"{SEZON}'nin \d+\. haftasına", f"{SEZON}'nin {HAFTA}. haftasına"),
                 (rf"\({SEZON}, ilk \d+ hafta\)", f"({SEZON}, ilk {HAFTA} hafta)"),
                 (r"Tüm maçlar \(\d+ hafta\)", f"Tüm maçlar ({HAFTA} hafta)"),
                 (rf"{SEZON} \d+ maç, \d+\. hafta dahil", f"{SEZON} {nS} maç, {HAFTA}. hafta dahil"),
                 (r"\d+\. hafta sonuçları TFF", f"{HAFTA}. hafta sonuçları TFF"),
                 (r"Sezonun ilk \d+ haftası", f"Sezonun ilk {HAFTA} haftası"),
                 (r"\d+ haftalık küçük örneklem", f"{HAFTA} haftalık küçük örneklem")]:
    Y = re.sub(pat, rep, Y)
print("hafta:", HAFTA, "son maç:", TARIH, "oyuncu:", len(R))
if Y == H:
    print("değişiklik yok; index.html aynen kaldı")
else:
    open(f"{ROOT}/index.html", "w", encoding="utf-8", newline="\n").write(sifrele.sifrele(Y, USER, PW, sifrele.tuz(eski_sayfa)))
    print("index.html yeniden şifrelendi")
if os.environ.get("SL_ACIK_YAZ"):   # yerelde kontrol için şifresiz kopya (depoya girmez, .gitignore)
    open(f"{ROOT}/uygulama_acik.html", "w", encoding="utf-8", newline="\n").write(Y)
