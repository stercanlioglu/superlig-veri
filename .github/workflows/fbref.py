# FBref Süper Lig 2026-27: takım ve oyuncu tabloları -> data/fbref/2026-27/*.csv
import requests, pandas as pd, time, re, io, os, sys
from bs4 import BeautifulSoup, Comment
SEASON = "2026-2027"; OUT = "data/fbref/2026-27"; os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) superlig-veri (kisisel analiz, dakikada <10 istek)"}
BASE = f"https://fbref.com/en/comps/26/{SEASON}"
PAGES = {  # sayfa adı -> url soneki
    "genel": f"{BASE}/{SEASON}-Super-Lig-Stats",
    "oyuncu_standart": f"{BASE}/stats/{SEASON}-Super-Lig-Stats",
    "oyuncu_sut": f"{BASE}/shooting/{SEASON}-Super-Lig-Stats",
    "oyuncu_pas": f"{BASE}/passing/{SEASON}-Super-Lig-Stats",
    "oyuncu_top": f"{BASE}/possession/{SEASON}-Super-Lig-Stats",
    "oyuncu_savunma": f"{BASE}/defense/{SEASON}-Super-Lig-Stats",
    "oyuncu_kaleci": f"{BASE}/keepers/{SEASON}-Super-Lig-Stats",
    "oyuncu_sure": f"{BASE}/playingtime/{SEASON}-Super-Lig-Stats",
    "oyuncu_cesitli": f"{BASE}/misc/{SEASON}-Super-Lig-Stats",
}
def get(url):
    for i in range(3):
        r = requests.get(url, headers=H, timeout=60)
        if r.status_code == 200: return r.text
        if r.status_code == 429: print("429 bekle 60sn"); time.sleep(60); continue
        print("HTTP", r.status_code, url); return None
    return None
def tables(html):
    # FBref tabloların çoğunu HTML yorumu içinde saklar; yorumları açıp hepsini oku
    soup = BeautifulSoup(html, "html.parser")
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" in c: c.replace_with(BeautifulSoup(c, "html.parser"))
    out = {}
    for t in soup.find_all("table"):
        tid = t.get("id")
        if not tid: continue
        try:
            df = pd.read_html(io.StringIO(str(t)))[0]
        except Exception as e:
            print("okunamadı", tid, e); continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [(a + "_" + b if not str(a).startswith("Unnamed") else b) for a, b in df.columns]
        if "Rk" in df.columns: df = df[df["Rk"].astype(str) != "Rk"]  # tekrar eden başlık satırları
        out[tid] = df
    return out
n = 0
for name, url in PAGES.items():
    html = get(url); time.sleep(7)  # dakikada ~8 istek
    if not html: continue
    tb = tables(html)
    print(f"== {name}: {len(tb)} tablo")
    for tid, df in tb.items():
        if len(df) < 3: continue
        fn = f"{OUT}/{name}__{tid}.csv"; df.to_csv(fn, index=False); n += 1
        print(f"   {tid}: {df.shape}  sütunlar: {list(df.columns)[:8]}")
print("toplam csv:", n)
