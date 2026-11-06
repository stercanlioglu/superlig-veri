# WeKissPicks resmi API'sinden (salt okunur) Tahmin Ligi verisi üretir.
# Anahtar WKP_API_KEY ortam değişkeninden okunur; depoya YAZILMAZ ve çıktıya basılmaz (depo herkese açık).
# Ham tahminler de diske yazılmaz: her çalışmada tüm haftalar yeniden çekilir (~25 istek), yalnızca özet uygulamaya girer.
#
# Puan kuralı: tam skor 3, yalnızca doğru sonuç (1/X/2) 1.
# Kullanıcı ağırlığı: geçmiş ortalama puan, havuz ortalamasına doğru küçültülmüş ((puan + K*ort) / (n + K), K=10).
# Grup görüşü: ağırlıklı skor payları; 1X2 olasılığı modele doğru yumuşatılır (az oyda tek kişi sonucu belirlemesin).
# Karma = %75 model + %25 grup. Karma testi, ağırlıkları yalnızca maçtan önceki haftalarla hesaplar (sızıntı yok).
import math, time
from collections import defaultdict
import numpy as np, requests
from scipy.stats import poisson

API = "https://wekisspicks.com/api/public/v1/super-lig/predictions"
UA = {"User-Agent": "superlig-veri/1.0 (kisisel analiz)"}
K_AG, KARMA_W, C_YUM, MIN_N = 10, 0.25, 3.0, 20
TOK = {"galatasaray": "Galatasaray", "fenerbahce": "Fenerbahce", "besiktas": "Besiktas", "trabzonspor": "Trabzonspor", "basaksehir": "Buyuksehyr",
       "alanyaspor": "Alanyaspor", "amed": "Amedspor", "corum": "Corum", "eyup": "Eyupspor", "genclerbirligi": "Genclerbirligi", "goztep": "Goztep",
       "kasimpasa": "Kasimpasa", "kocaelispor": "Kocaelispor", "konyaspor": "Konyaspor", "rizespor": "Rizespor", "samsunspor": "Samsunspor",
       "gaziantep": "Gaziantep", "erzurum": "Erzurum BB"}


def takim(ad, sade):
    k = " ".join(sade(ad))
    for t, m in TOK.items():
        if t in k: return m
    return None


# ---------------- API ----------------
def _al(anahtar, hafta):
    for deneme in range(4):
        r = requests.get(API, params={"week": hafta}, headers={**UA, "X-API-Key": anahtar}, timeout=40)
        if r.status_code == 200: return r.json()
        if r.status_code == 429: time.sleep(35); continue
        if r.status_code in (400, 404): return None
        try: kod = r.json().get("error")
        except Exception: kod = "?"
        raise RuntimeError(f"WeKissPicks API HTTP {r.status_code} ({kod})")   # anahtar yazdırılmaz
    raise RuntimeError("WeKissPicks API: istek sınırı aşıldı (429)")


def indir(anahtar, sade, max_hafta=40):
    """Tüm haftalar -> [{hafta, h, a, kick (UTC ISO), skor|None, tahmin:[(uid, ev, dep)]}]. İki hafta üst üste tahmin yoksa durur."""
    import datetime as dt
    maclar, bos = [], 0
    for hafta in range(1, max_hafta + 1):
        d = _al(anahtar, hafta)
        if not d or not d.get("matches"): break
        n = 0
        for m in d["matches"]:
            h, a = takim(m["home_team"], sade), takim(m["away_team"], sade)
            if not h or not a:
                print(f"  uyarı: takım adı eşleşmedi: {m['home_team']} - {m['away_team']}"); continue
            s = m.get("official_score")
            tah = [(p["user_id"], int(p["home"]), int(p["away"])) for p in m["predictions"] if p.get("home") is not None and p.get("away") is not None]
            n += len(tah)
            maclar.append({"hafta": hafta, "h": h, "a": a, "kick": dt.datetime.fromisoformat(m["kickoff_at"]), "skor": (int(s["home"]), int(s["away"])) if s else None, "tahmin": tah})
        bos = bos + 1 if n == 0 else 0
        if bos >= 2: break
        time.sleep(1.0)
    return maclar


# ---------------- hesap yardımcıları ----------------
def sg(i, j): return 0 if i > j else 1 if i == j else 2
def pts(t, s): return 3 if t == s else 1 if sg(*t) == sg(*s) else 0


def _tau(i, j, lh, la, rho):
    if i == 0 and j == 0: return 1 - lh * la * rho
    if i == 0 and j == 1: return 1 + lh * rho
    if i == 1 and j == 0: return 1 + la * rho
    if i == 1 and j == 1: return 1 - rho
    return 1.0


def skor_matrisi(lh, la, rho, n=8):
    P = np.array([[poisson.pmf(i, lh) * poisson.pmf(j, la) * _tau(i, j, lh, la, rho) for j in range(n + 1)] for i in range(n + 1)])
    return P / P.sum()


def skor_sec(P, pres, mod="opt"):
    """opt: beklenen puanı (sonuç olasılığı + 2×skor olasılığı) en yüksek skor; top: en olası skor."""
    best = None
    for i in range(P.shape[0]):
        for j in range(P.shape[1]):
            e = (pres[sg(i, j)] + 2 * P[i, j]) if mod == "opt" else P[i, j]
            if best is None or e > best[0] + 1e-12: best = (e, i, j)
    return best[1], best[2]


def grup(tahmin, W, onsel, model_p):
    """-> (skor payları sözlüğü, yumuşatılmış 1X2, ağırlık toplamı)"""
    pay, sw = defaultdict(float), 0.0
    for u, a, b in tahmin:
        w = W.get(u, onsel); pay[(a, b)] += w; sw += w
    sonuc = np.zeros(3)
    for (a, b), v in pay.items(): sonuc[sg(a, b)] += v
    gp = (sonuc + C_YUM * np.asarray(model_p)) / (sw + C_YUM)
    return {s: v / sw for s, v in pay.items()}, gp, sw


def pay_matrisi(pay, n=8):
    G = np.zeros((n + 1, n + 1))
    for (a, b), v in pay.items():
        if a <= n and b <= n: G[a, b] += v
    return G


def agirliklar(maclar, onsel):
    d = {}
    for m in maclar:
        for u, a, b in m["tahmin"]:
            x = d.setdefault(u, [0, 0]); x[0] += 1; x[1] += pts((a, b), m["skor"])
    return {u: (x[1] + K_AG * onsel) / (x[0] + K_AG) for u, x in d.items()}


def _ci(x, tohum=0, B=5000):
    x = np.asarray(x, float); rng = np.random.default_rng(tohum)
    bs = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
    return [round(float(v), 3) for v in np.percentile(bs, [2.5, 97.5])]


# ---------------- ana üretim ----------------
def uret(maclar, onbellek, tahmin_fn, rho, simdi):
    """maclar: indir() çıktısı. onbellek: {(h,a): (p3, lh, la)} biten maçların yürüyen model tahmini.
    tahmin_fn(h,a) -> (p3, skor matrisi): güncel modelle (oynanmamış maçlar ve önbellekte olmayanlar için)."""
    bit = [m for m in maclar if m["skor"] is not None and m["tahmin"]]
    if not bit: return None
    for m in bit:
        c = onbellek.get((m["h"], m["a"]))
        if c:   # yürüyen tahmin: olasılık her zaman önbellekten; gol beklentisi boşsa (yeni çıkan takım) yalnızca matris güncel modelden
            m["p"] = np.asarray(c[0], float)
            m["P"] = skor_matrisi(c[1], c[2], rho) if not any(math.isnan(v) for v in c[1:]) else tahmin_fn(m["h"], m["a"])[1]
        else: m["p"], m["P"] = (lambda r: (np.asarray(r[0], float), r[1]))(tahmin_fn(m["h"], m["a"]))
        m["ms"] = skor_sec(m["P"], m["p"], "opt")                # model: puan-optimum skor
        m["mt"] = skor_sec(m["P"], m["p"], "top")                # model: en olası skor
    # --- insanlar
    U = {}
    for m in bit:
        for u, a, b in m["tahmin"]:
            q = pts((a, b), m["skor"]); d = U.setdefault(u, [0, 0, 0, 0]); d[0] += 1; d[1] += q; d[2] += q == 3; d[3] += q >= 1
    tn, tp, te, tr = (sum(d[i] for d in U.values()) for i in range(4))
    onsel = tp / tn
    uzun = sorted(U)
    kisa = next(({u: u[:n] for u in uzun} for n in (10, 12, 16, 99) if len({u[:n] for u in uzun}) == len(uzun)))   # ekranda kısa, benzersiz kod
    rows = [[kisa[u], d[0], int(d[1]), int(d[2]), int(d[3]), round(d[1] / d[0], 3), round((d[1] + K_AG * onsel) / (d[0] + K_AG), 3)] for u, d in U.items() if d[0] >= MIN_N]
    rows.sort(key=lambda r: (-r[6], -r[5], -r[1]))
    # --- model satırları
    def mrow(ad, anahtar):
        q = [pts(m[anahtar], m["skor"]) for m in bit]
        return [ad, len(bit), int(sum(q)), int(sum(v == 3 for v in q)), int(sum(v >= 1 for v in q)), round(sum(q) / len(q), 3)]
    mod = [mrow("MODEL (puan-optimum)", "ms"), mrow("MODEL (en olası)", "mt")]
    mq = np.array([pts(m["ms"], m["skor"]) for m in bit])
    hq = np.array([np.mean([pts((a, b), m["skor"]) for _, a, b in m["tahmin"]]) for m in bit])
    # --- kaç kullanıcıyı geçiyor (kullanıcının oynadığı maçlarda modelin puanıyla)
    mpm = {(m["h"], m["a"]): q for m, q in zip(bit, mq)}; gec = yen = 0
    for u, d in U.items():
        if d[0] < MIN_N: continue
        mt = sum(mpm[(m["h"], m["a"])] for m in bit if any(uu == u for uu, _, _ in m["tahmin"]))
        gec += d[1] < mt; yen += d[1] > mt
    # --- karma testi: ağırlıklar yalnızca maçtan önceki haftalarla (sızıntı yok)
    KW = [0, KARMA_W, 0.5, 1.0]; tst = {w: ([], []) for w in KW}
    for hf in sorted(set(m["hafta"] for m in bit)):
        once = [m for m in bit if m["hafta"] < hf]
        on = (sum(pts((a, b), m["skor"]) for m in once for _, a, b in m["tahmin"]) / max(1, sum(len(m["tahmin"]) for m in once))) if once else onsel
        Wt = agirliklar(once, on) if once else {}
        for m in [x for x in bit if x["hafta"] == hf]:
            pay, gp, _ = grup(m["tahmin"], Wt, on, m["p"]); G = pay_matrisi(pay); y = sg(*m["skor"])
            for w in KW:
                pb = (1 - w) * m["p"] + w * gp; Pb = (1 - w) * m["P"] + w * G
                tst[w][0].append(pts(skor_sec(Pb, pb, "opt"), m["skor"])); tst[w][1].append(-math.log(max(float(pb[y]), 1e-9)))
    kal = {"w": KW, "pts": [round(float(np.mean(tst[w][0])), 3) for w in KW], "ll": [round(float(np.mean(tst[w][1])), 4) for w in KW],
           "ci25": _ci(np.array(tst[KARMA_W][0]) - np.array(tst[0][0]))}
    # --- oynanmamış maçlar: model, grup ve karma
    W = agirliklar(bit, onsel); up = []
    for m in sorted(maclar, key=lambda x: x["kick"]):
        if m["skor"] is not None or not m["tahmin"] or m["kick"] <= simdi: continue
        p, Pm = tahmin_fn(m["h"], m["a"]); p = np.asarray(p, float)
        pay, gp, _ = grup(m["tahmin"], W, onsel, p); G = pay_matrisi(pay)
        pk = (1 - KARMA_W) * p + KARMA_W * gp; Pk = (1 - KARMA_W) * Pm + KARMA_W * G
        top = sorted(pay.items(), key=lambda kv: -kv[1])[:3]
        up.append([f"{m['hafta']}. Hafta", m["h"], m["a"], [round(float(v), 3) for v in p], list(skor_sec(Pm, p, "opt")),
                   [round(float(v), 3) for v in pk], list(skor_sec(Pk, pk, "opt")), len(m["tahmin"]), f"{top[0][0][0]}-{top[0][0][1]}",
                   [round(float(v), 3) for v in gp], m["h"], m["a"], [[f"{a}-{b}", round(v, 3)] for (a, b), v in top]])
    return {"rows": rows, "mod": mod, "up": up, "human_avg": round(onsel, 3), "human_ex": round(te / tn, 3), "human_res": round(tr / tn, 3),
            "nmatch": len(bit), "diff": round(float((mq - hq).mean()), 3), "ci": _ci(mq - hq), "beat": [int(gec), int(yen), len(rows)],
            "w": KARMA_W, "kal": kal}
