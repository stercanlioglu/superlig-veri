import os, re, time, datetime, json
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
S = requests.Session(); S.headers.update(UA)
SLEEP = 1.0

def get(url, tries=3):
    for k in range(tries):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200 and len(r.content) > 200:
                return r.content
            print("  HTTP", r.status_code, url)
        except Exception as e:
            print("  hata", type(e).__name__, url)
        time.sleep(3 * (k + 1))
    return None

# 1) football-data.co.uk
os.makedirs("data/fd", exist_ok=True)
for y in range(2019, 2027):
    code = f"{str(y)[2:]}{str(y+1)[2:]}"; name = f"T1_{y}-{str(y+1)[2:]}.csv"
    for host in ("https://football-data.co.uk", "https://www.football-data.co.uk"):
        b = get(f"{host}/mmz4281/{code}/T1.csv")
        if b:
            with open(f"data/fd/{name}", "wb") as f: f.write(b)
            print("fd tamam", name, len(b)); break
    else:
        print("fd BASARISIZ", name)
    time.sleep(SLEEP)

# 2) TFF
SEASON = "2026-27"
os.makedirs(f"data/tff/{SEASON}/hafta", exist_ok=True); os.makedirs(f"data/tff/{SEASON}/mac", exist_ok=True)
today = datetime.date.today(); idx = {}
for w in range(1, 35):
    b = get(f"https://www.tff.org/Default.aspx?pageID=198&hafta={w}")
    time.sleep(SLEEP)
    if not b: continue
    html = b.decode("utf-8", "ignore")
    open(f"data/tff/{SEASON}/hafta/hafta_{w:02d}.html", "w", encoding="utf-8").write(html)
    last = None
    for m in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4})|pageId=29&(?:amp;)?macId=(\d+)", html, re.I):
        if m.group(4) is None:
            try: last = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError: pass
        else:
            idx.setdefault(m.group(4), {"hafta": w, "tarih": last.isoformat() if last else None})
print("bulunan mac:", len(idx))
json.dump(idx, open(f"data/tff/{SEASON}/index.json", "w"), indent=1)
n = 0
for mid, info in sorted(idx.items()):
    d = info["tarih"]
    if d and datetime.date.fromisoformat(d) > today: continue
    b = get(f"https://www.tff.org/Default.aspx?pageId=29&macId={mid}")
    time.sleep(SLEEP)
    if b:
        open(f"data/tff/{SEASON}/mac/{mid}.html", "wb").write(b); n += 1
print("kaydedilen mac sayfasi:", n)
