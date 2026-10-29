# FotMob takım/oyuncu adlarını model (football-data) ve TFF adlarıyla eşleştirir.
import re, unicodedata

def sade(s):
    s = str(s).replace("ı", "i").replace("İ", "I").replace("ş", "s").replace("Ş", "S").replace("ğ", "g").replace("Ğ", "G").replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s).split()

FM_TAKIM = {"amed sportif": "Amedspor", "basaksehir": "Buyuksehyr", "goztepe": "Goztep", "corum fk": "Corum", "erzurumspor fk": "Erzurum BB",
            "gaziantep fk": "Gaziantep", "rizespor": "Rizespor", "caykur rizespor": "Rizespor", "erzurumspor": "Erzurum BB"}

def takim(fm_ad, model_adlari):
    k = " ".join(sade(fm_ad))
    if k in FM_TAKIM: return FM_TAKIM[k]
    for m in model_adlari:
        if " ".join(sade(m)) == k: return m
    return None

def _uyum(fm, tff):
    """FotMob ad parçalarının TFF tam adında bulunma oranı (4+ harfte önek eşleşmesi kabul)."""
    bul = 0
    for f in fm:
        if any(t == f or (len(f) >= 4 and (t.startswith(f) or f.startswith(t)) and len(t) >= 4) for t in tff): bul += 1
    return bul / len(fm)

def oyuncular(fm_rows, tff_rows):
    """fm_rows/tff_rows: [(anahtar, ad, takim, dakika)]. Aynı takımda en iyi ad uyumu, eşitlikte dakika yakınlığı. -> {tff_anahtar: fm_anahtar}"""
    out, kullanilan = {}, set()
    adaylar = []
    for fk, fad, ft, fdk in fm_rows:
        fs = sade(fad)
        if not fs: continue
        for tk, tad, tt, tdk in tff_rows:
            if tt != ft: continue
            u = _uyum(fs, sade(tad))
            if u >= 0.5 and (u == 1 or len(fs) == 1 or fs[-1] in sade(tad)):
                adaylar.append((-u, abs((fdk or 0) - (tdk or 0)), fk, tk))
    for _, _, fk, tk in sorted(adaylar):
        if fk in kullanilan or tk in out: continue
        out[tk] = fk; kullanilan.add(fk)
    # takma adlar (Fabinho, Show...): aynı takımda dakikası ±15 tutan tek eşleşmemiş aday
    kalan_fm = [r for r in fm_rows if r[0] not in kullanilan and (r[3] or 0) > 0]
    for tk, tad, tt, tdk in tff_rows:
        if tk in out or not tdk: continue
        c = [r for r in kalan_fm if r[2] == tt and abs((r[3] or 0) - tdk) <= 15 and r[0] not in kullanilan]
        if len(c) == 1: out[tk] = c[0][0]; kullanilan.add(c[0][0])
    return out
