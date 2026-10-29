"""Süper Lig tahmin motoru — Faz 1 omurga.
Veri: football-data.co.uk aynası (footballcsv), 2019-20 … 2023-24 sonuçlar.
Modeller: Elo (ev avantajlı), Dixon–Coles (zaman ağırlıklı Poisson), birleşik.
Doğrulama: zamana göre ileri yürüyen test (rolling), log loss / RPS / Brier, taban çizgilerle karşılaştırma.
"""
import glob, json, math, os, re, sys
from datetime import datetime
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

D = os.path.dirname(os.path.abspath(__file__))

# ---------- 1. veri ----------
def load():
    rows = []
    for f in sorted(glob.glob(f"{D}/tr_*.csv")):
        season = re.search(r"tr_(\d{4}-\d{2})", f).group(1)
        df = pd.read_csv(f)
        for _, r in df.iterrows():
            if not isinstance(r["FT"], str) or "-" not in r["FT"]: continue
            hg, ag = map(int, r["FT"].split("-"))
            rows.append({"season": season, "date": datetime.strptime(r["Date"], "%a %b %d %Y"),
                         "home": r["Team 1"].strip(), "away": r["Team 2"].strip(), "hg": hg, "ag": ag})
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["res"] = np.sign(df.hg - df.ag)  # 1 ev, 0 beraberlik, -1 dep
    return df

# ---------- 2. Elo ----------
class Elo:
    def __init__(self, k=24, home_adv=90, start=1500, regress=0.1):
        self.k, self.ha, self.start, self.regress = k, home_adv, start, regress
        self.r = {}; self.last_season = {}
    def get(self, t): return self.r.get(t, self.start)
    def new_season(self, t, season):
        if self.last_season.get(t) not in (None, season):
            self.r[t] = self.get(t) + self.regress * (self.start - self.get(t))
        self.last_season[t] = season
    def expect(self, h, a):
        return 1 / (1 + 10 ** ((self.get(a) - self.get(h) - self.ha) / 400))
    def update(self, h, a, hg, ag):
        e = self.expect(h, a); s = 1 if hg > ag else 0.5 if hg == ag else 0
        mult = 1 + math.log1p(abs(hg - ag)) if hg != ag else 1   # gol farkı çarpanı
        d = self.k * mult * (s - e)
        self.r[h] = self.get(h) + d; self.r[a] = self.get(a) - d
        return e

def elo_to_probs(e_home, draw_base=0.22):
    """Elo beklentisini 1X2'ye çevir: beraberlik olasılığı dengeli maçta en yüksek."""
    d = draw_base * (1 - abs(2 * e_home - 1)) ** 0.5 + 0.12
    ph = (1 - d) * e_home; pa = (1 - d) * (1 - e_home)
    return np.array([ph, d, pa])

# ---------- 3. Dixon–Coles ----------
def dc_tau(x, y, lh, la, rho):
    if x == 0 and y == 0: return 1 - lh * la * rho
    if x == 0 and y == 1: return 1 + lh * rho
    if x == 1 and y == 0: return 1 + la * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0

def dc_fit(df, ref_date, xi=0.0055, init=None):
    """df: ref_date öncesi maçlar. xi: günlük zaman azalma (0.0055 ≈ 4 ayda yarı ağırlık)."""
    teams = sorted(set(df.home) | set(df.away)); idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    h = df.home.map(idx).values; a = df.away.map(idx).values; hg = df.hg.values; ag = df.ag.values
    w = np.exp(-xi * (ref_date - df.date).dt.days.values)
    def unpack(p):
        att = p[:n]; dfn = p[n:2 * n]; ha, rho = p[2 * n], p[2 * n + 1]
        return att, dfn, ha, rho
    def nll(p):
        att, dfn, ha, rho = unpack(p)
        att = att - att.mean()
        lh = np.exp(att[h] + dfn[a] + ha); la = np.exp(att[a] + dfn[h])
        ll = poisson.logpmf(hg, lh) + poisson.logpmf(ag, la)
        tau = np.array([dc_tau(x, y, l1, l2, rho) for x, y, l1, l2 in zip(hg, ag, lh, la)])
        ll += np.log(np.clip(tau, 1e-6, None))
        return -(w * ll).sum()
    p0 = init if init is not None and len(init) == 2 * n + 2 else np.concatenate([np.zeros(n), np.full(n, 0.0), [0.25, -0.05]])
    res = minimize(nll, p0, method="L-BFGS-B", options={"maxiter": 300})
    att, dfn, ha, rho = unpack(res.x); att = att - att.mean()
    return {"teams": teams, "att": dict(zip(teams, att)), "def": dict(zip(teams, dfn)), "ha": ha, "rho": rho, "x": res.x,
            "mu": float(np.exp(dfn.mean()))}

def dc_predict(m, home, away, maxg=8):
    att, dfn = m["att"], m["def"]
    if home not in att or away not in att: return None
    lh = math.exp(att[home] + dfn[away] + m["ha"]); la = math.exp(att[away] + dfn[home])
    P = np.zeros((maxg + 1, maxg + 1))
    for x in range(maxg + 1):
        for y in range(maxg + 1):
            P[x, y] = poisson.pmf(x, lh) * poisson.pmf(y, la) * dc_tau(x, y, lh, la, m["rho"])
    P /= P.sum()
    ph = np.tril(P, -1).sum(); pd_ = np.trace(P); pa = np.triu(P, 1).sum()
    return {"lh": lh, "la": la, "p": np.array([ph, pd_, pa]), "matrix": P,
            "over25": P[np.add.outer(range(maxg + 1), range(maxg + 1)) > 2].sum(), "btts": P[1:, 1:].sum()}

# ---------- 4. metrikler ----------
def logloss(p, res):  # res: 1,0,-1
    i = {1: 0, 0: 1, -1: 2}[res]; return -math.log(max(p[i], 1e-9))
def rps(p, res):
    o = np.zeros(3); o[{1: 0, 0: 1, -1: 2}[res]] = 1
    return ((np.cumsum(p) - np.cumsum(o)) ** 2)[:2].sum() / 2
def brier(p, res):
    o = np.zeros(3); o[{1: 0, 0: 1, -1: 2}[res]] = 1; return ((p - o) ** 2).sum()

# ---------- 5. ileri yürüyen test ----------
def backtest(df, test_seasons, refit_days=7, verbose=True):
    elo = Elo(); recs = []; model = None; last_fit = None; init = None
    hist_freq = None
    for i, r in df.iterrows():
        for t in (r.home, r.away): elo.new_season(t, r.season)
        if r.season in test_seasons:
            train = df.iloc[:i]
            if model is None or (r.date - last_fit).days >= refit_days:
                tr = train[train.date >= r.date - pd.Timedelta(days=900)]
                model = dc_fit(tr, r.date, init=init); init = model["x"]; last_fit = r.date
                hf = train.res.value_counts(normalize=True); hist_freq = np.array([hf.get(1, .45), hf.get(0, .27), hf.get(-1, .28)])
            pe = elo_to_probs(elo.expect(r.home, r.away))
            dc = dc_predict(model, r.home, r.away)
            pdc = dc["p"] if dc else pe
            pens = 0.5 * pe + 0.5 * pdc
            recs.append({"date": r.date, "season": r.season, "home": r.home, "away": r.away, "hg": r.hg, "ag": r.ag, "res": r.res,
                         "elo_h": elo.get(r.home), "elo_a": elo.get(r.away),
                         "p_elo": pe, "p_dc": pdc, "p_ens": pens, "p_base": hist_freq, "p_unif": np.array([1/3] * 3),
                         "lh": dc["lh"] if dc else None, "la": dc["la"] if dc else None})
        elo.update(r.home, r.away, r.hg, r.ag)
    bt = pd.DataFrame(recs)
    out = {}
    for k in ["unif", "base", "elo", "dc", "ens"]:
        out[k] = {"logloss": bt.apply(lambda r: logloss(r["p_" + k], r.res), axis=1).mean(),
                  "rps": bt.apply(lambda r: rps(r["p_" + k], r.res), axis=1).mean(),
                  "brier": bt.apply(lambda r: brier(r["p_" + k], r.res), axis=1).mean(),
                  "acc": bt.apply(lambda r: [1, 0, -1][int(np.argmax(r["p_" + k]))] == r.res, axis=1).mean()}
    return bt, out, elo, model

if __name__ == "__main__":
    df = load()
    print(f"{len(df)} maç, {df.date.min().date()} → {df.date.max().date()}, {df.home.nunique()} takım")
    print("Sonuç dağılımı:", df.res.value_counts(normalize=True).round(3).to_dict())
    print("Ortalama gol: ev", round(df.hg.mean(), 2), "dep", round(df.ag.mean(), 2))
    bt, out, elo, model = backtest(df, {"2022-23", "2023-24", "2024-25"})
    print(f"\nİleri yürüyen test: {len(bt)} maç (2022-23 → 2024-25)")
    print(pd.DataFrame(out).T.round(4).to_string())
    # kalibrasyon: ensemble ev galibiyeti olasılığı dilimleri
    bt["ph"] = bt.p_ens.apply(lambda p: p[0]); bt["win"] = (bt.res == 1).astype(int)
    bt["bin"] = pd.cut(bt.ph, [0, .3, .4, .5, .6, .7, 1])
    print("\nKalibrasyon (ev galibiyeti):\n", bt.groupby("bin", observed=True).agg(n=("win", "size"), tahmin=("ph", "mean"), gercek=("win", "mean")).round(3).to_string())
    # güncel güç tablosu
    print("\nElo (son sezon sonu):")
    for t, r in sorted(elo.r.items(), key=lambda x: -x[1])[:20]: print(f"  {t:<22}{r:7.0f}")
    print("\nDixon–Coles hücum/savunma (son fit):  ha =", round(model["ha"], 3), " rho =", round(model["rho"], 3))
    for t in sorted(model["att"], key=lambda t: -(model["att"][t] - model["def"][t]))[:20]:
        print(f"  {t:<22} hücum {model['att'][t]:+.2f}  savunma {model['def'][t]:+.2f}")
    bt.to_pickle(f"{D}/backtest.pkl")
    json.dump({"elo": elo.r, "dc": {"att": model["att"], "def": model["def"], "ha": model["ha"], "rho": model["rho"]}, "metrics": out},
              open(f"{D}/superlig_model.json", "w"), ensure_ascii=False, indent=1, default=float)
