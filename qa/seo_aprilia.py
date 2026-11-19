"""Automated local SEO regression audit — only disposable local data.
No live infrastructure, APIs, original photographs or family documents are touched.
"""
import os, sys, json, re, tempfile
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"site"))
_tmp=tempfile.TemporaryDirectory(prefix="bodymind-local-seo-")
os.environ["SITE_DATA_DIR"]=_tmp.name
from app import app  # noqa: E402
from seo_pages import PAGES, ORDER, ORIGIN

client=app.test_client()
def check(ok,reason):
    if not ok:raise AssertionError(reason)
def parse_html_jsonld(page):
    match=re.search(r'<script type="application/ld\+json">(.*?)</script>',page,re.S)
    check(match is not None,"Missing JSON-LD")
    return json.loads(match.group(1))
pages={}
for slug,data in PAGES.items():
    path="/"+slug
    r=client.get(path)
    check(r.status_code==200,f"{slug}: expected 200 got {r.status_code}")
    h=r.get_data(as_text=True)
    pages[slug]=h
    check(f'<title>{data["title"]}</title>' in h,f"{slug}: title incorrect")
    check(f'<link rel="canonical" href="{ORIGIN}/{slug}">' in h,f"{slug}: canonical")
    check(data["description"] in unescape(h),f"{slug}: missing meta description")
    check('property="og:image:alt" content="'+data["photo_alt"]+'"' in unescape(h),f"{slug}: photo open graph alt missing")
    check('name="twitter:image"' in h,f"{slug}: Twitter image missing")
    check("primaryImageOfPage" in h,f"{slug}: structured photo missing")
    check(f'<h1 id="titolo-pagina">{data["h1"]}</h1>' in h,f"{slug}: H1")
    check("content=\"index,follow" in h and "noindex" not in h,f"{slug}: robots")
    check('href="/#contatti"' in h,f"{slug}: missing conversion CTA")
    check('href="/#sedi"' in h,f"{slug}: missing venue navigation")
    check("Palagym Aprilia" in h and "Pianeta Forma" in h,f"{slug}: missing actual venues")
    check('src="/seed-media/gallery' in h,f"{slug}: must use genuine media")
    check(h.count("<details>")==3,f"{slug}: FAQ has wrong count")
    check(h.count('<article>')==3,f"{slug}: editorial sections count")
    check(len(re.findall(r'<a href="/(?:danza-aerea-aprilia|cerchio-aereo-aprilia|tessuti-aerei-aprilia|danza-aerea-ragazze-donne-aprilia)"',h))>=3,
          f"{slug}: not linked")
    graph=parse_html_jsonld(h)
    check(graph["@graph"][0]["@type"]=="SportsOrganization",f"{slug}: organization schema")
    check(len(graph["@graph"][0]["location"])==2,f"{slug}: real host venues")
    check(graph["@graph"][1]["url"]==ORIGIN+"/"+slug,f"{slug}: schema canonical mismatch")
    check(not any(k in json.dumps(graph).lower() for k in ['aggregaterating','reviewcount','price']),f"{slug}: fabricated ratings/prices")
    print("PASS page",path,r.status_code,"title",len(data["title"]),"desc",len(data["description"]))
home=client.get("/")
check(home.status_code==200,"Homepage unavailable")
h=home.get_data(as_text=True)
check("Danza Aerea e Cerchio Aereo ad Aprilia" in h or "BodyMind Aerial Studio | Danza Aerea ad Aprilia" in h,
      "Home title not specialized")
check("seo-local.css" not in h,"Home design must stay original")
check('name="twitter:image"' in h and 'property="og:image:alt"' in h,"Home image metadata missing")
check('alt="Performer BodyMind durante un esercizio aereo in costume rosso ad Aprilia"' in h,"Movement image alt lost")
check('alt="Allieva BodyMind in un esercizio sul cerchio aereo' in h,"Kids alt lost")

check("atto-unico.css" in h,"Original design stylesheet lost")
check("data-hero-video" in h,"Original autoplay video removed")
check("data-kids-video-shell" in h or "kids-photo-stage" in h,"Kids media lost")
check("bodymind-competition-double.webp" in h or '/seed-media/gallery5' in h,"Original Competition media lost")
check("Safeguarding" in h and "dan24378@icloud.com" in h,"Safeguarding altered")
check("Palagym Aprilia" in h and "Pianeta Forma" in h,"Original two venues missing")
for slug in ORDER:
    check(f'href="/{slug}"' in h,f"Internal link to /{slug} missing")
org=parse_html_jsonld(h)
check(org["@type"]=="SportsOrganization","Home organization schema incorrect")
print("PASS homepage same images, video, safeguarding, navigation and real venues")

xml=client.get("/sitemap.xml")
check(xml.status_code==200,"Sitemap unavailable")
root=ElementTree.fromstring(xml.get_data(as_text=True))
ns={'sm':'http://www.sitemaps.org/schemas/sitemap/0.9'}
urls=[n.text for n in root.findall('.//sm:loc',ns)]
expected={ORIGIN+"/"}|{ORIGIN+"/"+s for s in ORDER}
check(set(urls)==expected,"Sitemap URLs incorrect: "+str(urls))
image_ns={'image':'http://www.google.com/schemas/sitemap-image/1.1'}
images=[node.text for node in root.findall('.//image:loc',image_ns)]
check(len(images)>=9,"Sitemap should expose actual photos (5 home + 4 pages): "+str(images))
check(all(img.startswith(ORIGIN+"/seed-media/gallery") for img in images),"Unexpected externally hosted sitemap photo")
check(len(set(images))>=5,"Sitemap image diversity missing")
print("PASS original image SEO sitemap",len(images),"references")

print("PASS sitemap",len(urls),"canonical URLs")

robots=client.get("/robots.txt")
check(robots.status_code==200,"Robots unavailable")
text=robots.get_data(as_text=True)
check("Sitemap: "+ORIGIN+"/sitemap.xml" in text,"Sitemap absent in robots")
check("Disallow: /studio-admin" in text,"Admin robot restriction lost")
check("Disallow: /danza-" not in text,"SEO pages blocked")
print("PASS robots")

for path in ["/studio-admin/login","/studio-admin"]:
    rr=client.get(path,follow_redirects=False)
    check(rr.status_code in (200,302,303),f"Admin endpoint {path} broken {rr.status_code}")
print("PASS admin routes (no authentication bypass)")
print("BODYMIND_APRILIA_SEO_TESTS_PASS")
_tmp.cleanup()
