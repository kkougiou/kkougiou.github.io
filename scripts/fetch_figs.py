import json, os, re, sys, time, urllib.request, urllib.parse
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
PAPERS = {
 "extinction-risk": "10.3390/biology10030195",
 "endemism-centres": "10.3390/biology10020072",
 "crete-diversity": "10.3390/d12070270",
 "network-biogeography": "10.1111/jbi.12920",
}
def get(url, accept="*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.geturl(), r.read()
os.makedirs("figs", exist_ok=True)
log = {}
for slug, doi in PAPERS.items():
    d = f"figs/{slug}"; os.makedirs(d, exist_ok=True); log[slug] = []
    try:
        final, html = get("https://doi.org/" + doi, "text/html")
        html = html.decode("utf-8", "replace")
        log[slug].append(f"landing {final} {len(html)}")
        imgs = re.findall(r'(https?://[^"\']+?article_deploy/html/images/[^"\']+?-g\d+[^"\']*?\.(?:png|jpg))', html)
        imgs = sorted(set(i for i in imgs if "-550" not in i))
        caps = re.findall(r'<div class="html-caption"[^>]*>(.*?)</div>', html, re.S)
        open(f"{d}/captions.txt", "w").write("\n\n".join(re.sub(r"<[^>]+>", "", c).strip() for c in caps))
        for u in imgs:
            try:
                _, data = get(u); open(f"{d}/{u.rsplit('/',1)[1]}", "wb").write(data); log[slug].append("img " + u)
            except Exception as e: log[slug].append(f"imgfail {u} {e}")
            time.sleep(1)
    except Exception as e:
        log[slug].append(f"landing fail {e}")
    if not [f for f in os.listdir(d) if f.endswith((".png", ".jpg"))]:
        try:
            _, w = get("https://api.openalex.org/works/doi:" + doi)
            w = json.loads(w)
            locs = [l for l in w.get("locations", []) if l.get("pdf_url")]
            log[slug].append("oa pdfs " + str([l["pdf_url"] for l in locs]))
            for l in locs:
                try:
                    _, pdf = get(l["pdf_url"], "application/pdf")
                    if pdf[:4] == b"%PDF":
                        open(f"{d}/paper.pdf", "wb").write(pdf); log[slug].append("pdf ok " + l["pdf_url"]); break
                except Exception as e: log[slug].append(f"pdf fail {l['pdf_url']} {e}")
        except Exception as e: log[slug].append(f"openalex fail {e}")
json.dump(log, open("figs/log.json", "w"), indent=1)
print(json.dumps(log, indent=1))
