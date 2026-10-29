import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

def dc_fit(df, ref_date, xi=0.0055, ridge=1.5, init=None):
    """Dixon–Coles + ridge cezası: az maçı olan takımın katsayıları lig ortalamasına çekilir."""
    teams = sorted(set(df.home) | set(df.away)); idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    h = df.home.map(idx).values; a = df.away.map(idx).values; hg = df.hg.values; ag = df.ag.values
    w = np.exp(-xi * (ref_date - df.date).dt.days.values)
    m00 = (hg == 0) & (ag == 0); m01 = (hg == 0) & (ag == 1); m10 = (hg == 1) & (ag == 0); m11 = (hg == 1) & (ag == 1)
    def nll(p):
        att = p[:n] - p[:n].mean(); dfn = p[n:2 * n]; mu, ha, rho = p[2 * n], p[2 * n + 1], p[2 * n + 2]
        lh = np.exp(mu + att[h] + dfn[a] + ha); la = np.exp(mu + att[a] + dfn[h])
        ll = poisson.logpmf(hg, lh) + poisson.logpmf(ag, la)
        tau = np.ones_like(lh); tau[m00] = 1 - lh[m00] * la[m00] * rho; tau[m01] = 1 + lh[m01] * rho
        tau[m10] = 1 + la[m10] * rho; tau[m11] = 1 - rho
        ll += np.log(np.clip(tau, 1e-6, None))
        return -(w * ll).sum() + ridge * ((att ** 2).sum() + (dfn ** 2).sum())
    p0 = np.concatenate([np.zeros(2 * n), [0.2, 0.25, -0.05]])
    res = minimize(nll, p0, method="L-BFGS-B", bounds=[(-3, 3)] * (2 * n) + [(-1, 1), (-0.5, 1), (-0.3, 0.3)], options={"maxiter": 2000})
    att = res.x[:n] - res.x[:n].mean(); dfn = res.x[n:2 * n] + res.x[2 * n]
    return {"teams": teams, "att": dict(zip(teams, att)), "def": dict(zip(teams, dfn)), "ha": res.x[2 * n + 1], "rho": res.x[2 * n + 2], "ok": res.success}


def power_devig(o):
    inv = 1 / np.array(o, float)
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        if (inv ** k).sum() > 1: lo = k
        else: hi = k
    p = inv ** k; return p / p.sum()

