# Livesport maç önizlemelerinden eksik oyuncular -> data/livesport/<SEZON>/haberler.json
# 1 istek fikstür sayfası (gelecek maçlar sayfaya gömülü), sonra her maç için "haberler" sekmesi (robots.txt: /tr/mac/ izinli;
# /newsfeed/ yasak, kullanılmaz). Önizleme metninin kendisi saklanmaz; yalnızca ayıklanan bilgiler ve sayfa bağlantısı.
import requests, re, json, os, sys, time, html as H
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor"))
import eslestir
SEZON = "2026-27"; OUT = f"data/livesport/{SEZON}"; os.makedirs(OUT, exist_ok=True)
BASE = "https://www.livesport.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) superlig-veri (kisisel analiz, yavas)", "Accept-Language": "tr"}
TAKIMLAR = ["Alanyaspor", "Amedspor", "Besiktas", "Buyuksehyr", "Corum", "Erzurum BB", "Eyupspor", "Fenerbahce", "Galatasaray", "Gaziantep",
            "Genclerbirligi", "Goztep", "Kasimpasa", "Kocaelispor", "Konyaspor", "Rizespor", "Samsunspor", "Trabzonspor"]
GUN = 4   # önümüzdeki kaç günün maçları (önizleme maçtan ~2 gün önce yayımlanıyor)

def get(url):
    for k in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=40)
            if r.status_code == 200: return r.text
            print("  HTTP", r.status_code, url)
        except Exception as e:
            print("  hata", type(e).__name__, url)
        time.sleep(10 * (k + 1))
    return None

def eksikler(sayfa, ev_ad, dep_ad):
    """'Kilit oyuncular ve eksikler' bölümünden forma giyemeyecek / şüpheli oyuncular."""
    m = re.search(r"<h2>Kilit oyuncular ve eksikler</h2>(.*?)(<h2>|</article>|$)", sayfa, re.S)
    if not m: return None
    out = []
    for p in re.findall(r"<p>(.*?)</p>", m.group(1), re.S):
        for cumle in re.split(r"(?<=[.!?])\s*(?=[A-ZÇĞİÖŞÜ<])", p):   # bazı cümleler boşluksuz bitişik
            duz = H.unescape(re.sub(r"<[^>]+>", "", cumle))
            if re.search(r"giyemeyecek|oynayamayacak|forma giymeyecek|kadroda yer almayacak", duz): durum = "yok"
            elif re.search(r"şüpheli|belirsiz|giyip giyemeyeceği|son kararı", duz): durum = "supheli"
            else: continue
            neden = "ceza" if re.search(r"kart|ceza", duz) else "sakatlık" if re.search(r"sakat|yaralan|tedavi", duz) else "diğer"
            bas = duz.split(" ")[0]
            takim = ev_ad if bas.startswith(ev_ad.split()[0]) else dep_ad if bas.startswith(dep_ad.split()[0]) else None
            adlar = re.findall(r"<a [^>]*>(.*?)</a>", cumle)
            if not adlar:   # bağlantısız ad: fiilden önceki büyük harfli kelimeler
                k = re.search(r"((?:[A-ZÇĞİÖŞÜ][\w'’.-]+\s+){1,3})(?:sakatlığı nedeniyle\s+|bu maçta\s+|cezası nedeniyle\s+)?(?:forma giyemeyecek|oynayamayacak|forma giymeyecek)", duz)
                if k: adlar = [k.group(1).strip()]
            for ad in adlar:
                out.append({"takim": takim, "oyuncu": H.unescape(ad).strip(), "durum": durum, "neden": neden})
    return out

fik = get(f"{BASE}/tr/futbol/turkiye/super-lig/fikstur/")
if not fik: sys.exit("Livesport fikstür sayfası alınamadı")
simdi = time.time(); maclar = []
for r in fik.split("~AA÷")[1:]:
    d = dict(x.split("÷", 1) for x in ("AA÷" + r).split("¬") if "÷" in x)
    try: ts = int(d.get("AD", 0))
    except ValueError: continue
    if not (simdi - 3 * 3600 < ts < simdi + GUN * 86400): continue
    ev, dep = eslestir.takim(d.get("AE", ""), TAKIMLAR), eslestir.takim(d.get("AF", ""), TAKIMLAR)
    if not ev or not dep or any(x["mid"] == d["AA"] for x in maclar): continue   # fikstürde her maç iki kez geçiyor
    url = f"{BASE}/tr/mac/futbol/{d['WU']}-{d['PX']}/{d['WV']}-{d['PY']}/haberler/?mid={d['AA']}"
    maclar.append({"mid": d["AA"], "tarih": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)), "ev": ev, "dep": dep,
                   "ev_ad": d.get("AE"), "dep_ad": d.get("AF"), "hafta": d.get("ER"), "url": url})
print("gelecek maç:", len(maclar))
for m in maclar:
    time.sleep(4)
    s = get(m["url"])
    e = eksikler(s, m["ev_ad"], m["dep_ad"]) if s else None
    m["onizleme"] = e is not None; m["eksik"] = e or []
    for x in m["eksik"]: x["takim"] = m["ev"] if x["takim"] == m["ev_ad"] else m["dep"] if x["takim"] == m["dep_ad"] else None   # boşsa motor kadrodan bulur
    print(f"{m['tarih']} {m['ev']:>15s} - {m['dep']:<15s} önizleme:{'var' if m['onizleme'] else 'yok'}  eksik: {[(x['oyuncu'], x['takim'], x['durum'], x['neden']) for x in m['eksik']]}")
json.dump({"cekildi": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "maclar": maclar}, open(f"{OUT}/haberler.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
