import json, os, re, time, urllib.request, tarfile, io
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
def get(url, accept="*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Referer": "https://www.mdpi.com/"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.geturl(), r.read()
log = {}
MDPI = {"extinction-risk": ("biology", "biology-10-00195", "10.3390/biology10030195"),
        "endemism-centres": ("biology", "biology-10-00072", "10.3390/biology10020072"),
        "crete-diversity": ("diversity", "diversity-12-00270", "10.3390/d12070270")}
for slug, (j, art, doi) in MDPI.items():
    d = f"figs/{slug}"; os.makedirs(d, exist_ok=True); log[slug] = []
    for n in range(1, 13):
        for ext in ("png", "jpg"):
            u = f"https://pub.mdpi-res.com/{j}/{art}/article_deploy/html/images/{art}-g{n:03d}.{ext}"
            try:
                _, data = get(u)
                if len(data) > 2000:
                    open(f"{d}/{art}-g{n:03d}.{ext}", "wb").write(data); log[slug].append(f"ok {u} {len(data)}"); break
            except Exception as e:
                log[slug].append(f"fail {u} {e}")
        time.sleep(0.5)
    if not any(x.startswith("ok") for x in log[slug]):
        # PubMed Central open-access package
        try:
            _, r = get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json&resultType=lite")
            res = json.loads(r)["resultList"]["result"]
            pmcid = res[0].get("pmcid") if res else None
            log[slug].append(f"pmcid {pmcid}")
            if pmcid:
                _, x = get(f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}")
                m = re.search(rb'href="([^"]+\.tar\.gz)"', x)
                log[slug].append(f"oa {m.group(1) if m else x[:200]}")
                if m:
                    url = m.group(1).decode().replace("ftp://", "https://")
                    _, tgz = get(url)
                    with tarfile.open(fileobj=io.BytesIO(tgz)) as t:
                        for mem in t.getmembers():
                            if mem.name.lower().endswith((".jpg", ".png", ".gif")) and mem.size > 20000:
                                open(f"{d}/{os.path.basename(mem.name)}", "wb").write(t.extractfile(mem).read())
                                log[slug].append("pmc " + mem.name)
        except Exception as e:
            log[slug].append(f"pmc fail {e}")
# JBI 2017: look for a repository copy via CORE / Wiley figure assets
d = "figs/network-biogeography"; os.makedirs(d, exist_ok=True); log["network-biogeography"] = []
for u in ["https://core.ac.uk/works/138391682", "https://core.ac.uk/search?q=doi%3A%2210.1111%2Fjbi.12920%22",
          "https://onlinelibrary.wiley.com/doi/full/10.1111/jbi.12920"]:
    try:
        final, html = get(u, "text/html"); html = html.decode("utf-8", "replace")
        links = sorted(set(re.findall(r'https?://[^"\'\s<>]+?(?:\.pdf|/download/[^"\'\s<>]+)', html)))
        imgs = sorted(set(re.findall(r'https?://[^"\'\s<>]+?/cms/asset/[^"\'\s<>]+?\.(?:jpg|png)', html)))
        log["network-biogeography"].append(f"{u} -> {final} {len(html)} pdfs={links[:8]} imgs={imgs[:12]}")
        for i in imgs:
            try:
                _, data = get(i); open(f"{d}/{i.rsplit('/',1)[1]}", "wb").write(data)
            except Exception as e: log["network-biogeography"].append(f"imgfail {i} {e}")
        for l in links[:4]:
            try:
                _, pdf = get(l, "application/pdf")
                if pdf[:4] == b"%PDF" and b"Aegean" in pdf[:2000000]:
                    open(f"{d}/paper.pdf", "wb").write(pdf); log["network-biogeography"].append("pdf ok " + l); break
            except Exception as e: log["network-biogeography"].append(f"pdffail {l} {e}")
    except Exception as e:
        log["network-biogeography"].append(f"{u} fail {e}")
json.dump(log, open("figs/log.json", "w"), indent=1)
print(json.dumps({k: [x for x in v if not x.startswith('fail')] for k, v in log.items()}, indent=1))
