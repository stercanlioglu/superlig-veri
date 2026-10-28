# Kullanım: python oyuncu.py PARSE_CIKTI_KLASORU SEZON CIKTI_KLASORU
import sys, pandas as pd, numpy as np
src, sezon, out = sys.argv[1], sys.argv[2], sys.argv[3]
m = pd.read_csv(f"{src}/maclar.csv"); k = pd.read_csv(f"{src}/kadro.csv")
g = pd.read_csv(f"{src}/goller.csv"); c = pd.read_csv(f"{src}/kartlar.csv")
k = k[(k.rol == "ilk11") | k.giris.notna()].copy()          # sadece sahaya çıkanlar
k["dk"] = (k.cikis.fillna(90) - k.giris.fillna(0)).clip(0, 120)
k = k.merge(m[["macId", "tarih", "ev", "dep"]], on="macId")
k["takim"] = np.where(k.taraf == 1, k.ev, k.dep)
k["ilk11"] = (k.rol == "ilk11").astype(int)
g["ownk"] = (g.tip == "K").astype(int)
gk = g[g.ownk == 0].groupby(["macId", "oyuncu"]).agg(gol=("tip", "size"), penalti=("tip", lambda s: (s == "P").sum()),
      kafa=("tip", lambda s: (s == "H").sum()), ilk_gol_dk=("dakika", "min")).reset_index()
og = g[g.ownk == 1].groupby(["macId", "oyuncu"]).size().rename("kk_gol").reset_index()
c["sari"] = (c.alt == "Sarı Kart").astype(int); c["cift"] = (c.alt == "Çift Sarı Kart").astype(int); c["kirmizi"] = (c.alt == "Kırmızı Kart").astype(int)
ck = c.groupby(["macId", "oyuncu"])[["sari", "cift", "kirmizi"]].sum().reset_index()
P = k.merge(gk, on=["macId", "oyuncu"], how="left").merge(og, on=["macId", "oyuncu"], how="left").merge(ck, on=["macId", "oyuncu"], how="left")
for col in ("gol", "penalti", "kafa", "kk_gol", "sari", "cift", "kirmizi"): P[col] = P[col].fillna(0).astype(int)
P.insert(0, "sezon", sezon)
P[["sezon", "macId", "tarih", "takim", "oyuncu", "kisiId", "forma", "ilk11", "giris", "cikis", "dk", "gol", "penalti", "kafa", "kk_gol", "sari", "cift", "kirmizi"]].to_csv(f"{out}/oyuncu_mac.csv", index=False)
S = P.groupby(["sezon", "oyuncu", "kisiId"]).agg(takim=("takim", "last"), mac=("macId", "nunique"), ilk11=("ilk11", "sum"), dakika=("dk", "sum"),
      gol=("gol", "sum"), penalti=("penalti", "sum"), kafa=("kafa", "sum"), sari=("sari", "sum"), cift=("cift", "sum"), kirmizi=("kirmizi", "sum")).reset_index()
S["gol_90"] = (S.gol / S.dakika * 90).round(2); S["dk_mac"] = (S.dakika / S.mac).round(0)
takim_mac = P.groupby("takim").macId.nunique(); S["takim_mac"] = S.takim.map(takim_mac); S["oynama_orani"] = (S.mac / S.takim_mac).round(2)
S.sort_values(["gol", "dakika"], ascending=False).to_csv(f"{out}/oyuncu_sezon.csv", index=False)
print("oyuncu:", len(S), "oyuncu-mac:", len(P))
