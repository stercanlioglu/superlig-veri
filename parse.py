import re, glob, os, csv, sys, json
from bs4 import BeautifulSoup
BASE = sys.argv[1]; OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
def dk(s):
    m = re.search(r"(\d+)(?:\+(\d+))?\.?\s*dk", s or "")
    return (int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0) * 0.0, int(m.group(2)) if m.group(2) else 0) if m else (None, 0)
def tx(s, suffix):
    e = s.find(id=re.compile(re.escape(suffix) + "$")); return e.get_text(" ", strip=True) if e else None
rows = {k: [] for k in ("maclar", "goller", "kartlar", "kadro", "degisiklik")}
n = skipped = 0
for f in sorted(glob.glob(f"{BASE}/mac/*.html")):
    mid = os.path.basename(f)[:-5]
    s = BeautifulSoup(open(f, "rb").read().decode("cp1254", "ignore"), "html.parser")
    for t in s(["script", "style"]): t.decompose()
    sk1, sk2 = tx(s, "lblTakim1Skor"), tx(s, "Label12")
    if not (sk1 and sk2 and sk1.isdigit() and sk2.isdigit()): skipped += 1; continue
    h, a = tx(s, "lnkTakim1"), tx(s, "lnkTakim2"); tarih = tx(s, "lblTarih") or ""
    m = re.match(r"(\d\d)\.(\d\d)\.(\d{4})\s*-\s*(\d\d:\d\d)", tarih)
    date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None; time_ = m.group(4) if m else None
    ref = next((re.sub(r"\(Hakem\)$", "", e.get_text(strip=True)) for e in s.find_all(id=re.compile("lnkHakem$")) if e.get_text(strip=True).endswith("(Hakem)")), None)
    coaches = {}
    for side in (1, 2):
        g = s.find(id=re.compile(f"grdTakim{side}_rptTeknikKadro_ctl01_lnkTeknikSorumlu$")); coaches[side] = g.get_text(strip=True) if g else None
    rows["maclar"].append(dict(macId=mid, tarih=date, saat=time_, ev=h, dep=a, ev_gol=int(sk1), dep_gol=int(sk2), stadyum=tx(s, "lnkStad"), hakem=ref, ev_hoca=coaches[1], dep_hoca=coaches[2]))
    for side in (1, 2):
        pre = f"grdTakim{side}_"
        for e in s.find_all(id=re.compile(pre + r"rptGoller_ctl\d+_lblGol$")):
            mm = re.match(r"(.*?),\s*(\d+)(?:\+(\d+))?\.dk\s*\((\w)\)", e.get_text(strip=True))
            if mm: rows["goller"].append(dict(macId=mid, taraf=side, oyuncu=mm.group(1), dakika=int(mm.group(2)), uzatma=int(mm.group(3) or 0), tip=mm.group(4)))
        for e in s.find_all(id=re.compile(pre + r"rptKartlar_ctl\d+_lblKart$")):
            base = e["id"][:-len("lblKart")]; img = s.find(id=base + "k"); alt = (img.get("alt") if img else "") or ""
            d = s.find(id=base + "d"); mm = re.search(r"(\d+)", d.get_text() if d else "")
            tip = "cift_sari" if "ift" in alt else ("kirmizi" if "rm" in alt.lower() else "sari")
            rows["kartlar"].append(dict(macId=mid, taraf=side, oyuncu=e.get_text(strip=True), dakika=int(mm.group(1)) if mm else None, tip=tip, alt=alt))
        ins, outs = {}, {}
        for e in s.find_all(id=re.compile(pre + r"rptGirenler_ctl\d+_lblGiren$")):
            d = s.find(id=e["id"][:-len("lblGiren")] + "og"); mm = re.search(r"(\d+)", d.get_text() if d else ""); ins[e.get_text(strip=True)] = int(mm.group(1)) if mm else None
        for e in s.find_all(id=re.compile(pre + r"rptCikanlar_ctl\d+_lblCikan$")):
            d = s.find(id=e["id"][:-len("lblCikan")] + "oc"); mm = re.search(r"(\d+)", d.get_text() if d else ""); outs[e.get_text(strip=True)] = int(mm.group(1)) if mm else None
        for role, rep in (("ilk11", "rptKadrolar"), ("yedek", "rptYedekler")):
            for e in s.find_all(id=re.compile(pre + rep + r"_ctl\d+_lnkOyuncu$")):
                nm = e.get_text(strip=True); fn = s.find(id=e["id"][:-len("lnkOyuncu")] + "formaNo"); kid = re.search(r"kisiId=(\d+)", e.get("href", ""))
                giris = 0 if role == "ilk11" else ins.get(nm); cikis = outs.get(nm)
                rows["kadro"].append(dict(macId=mid, taraf=side, rol=role, oyuncu=nm, kisiId=kid.group(1) if kid else None, forma=(fn.get_text(strip=True).rstrip(".") if fn else None), giris=giris, cikis=cikis))
        for nm, mn in ins.items(): rows["degisiklik"].append(dict(macId=mid, taraf=side, yon="giren", oyuncu=nm, dakika=mn))
        for nm, mn in outs.items(): rows["degisiklik"].append(dict(macId=mid, taraf=side, yon="cikan", oyuncu=nm, dakika=mn))
    n += 1
for k, v in rows.items():
    with open(f"{OUT}/{k}.csv", "w", newline="", encoding="utf-8") as fh:
        if v:
            w = csv.DictWriter(fh, fieldnames=list(v[0].keys())); w.writeheader(); w.writerows(v)
print("ayrıştırılan maç:", n, "atlanan (oynanmamış):", skipped, {k: len(v) for k, v in rows.items()})
