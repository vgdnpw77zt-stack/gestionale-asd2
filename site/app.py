import os, json, secrets, urllib.request, re
from pathlib import Path
from functools import wraps
from copy import deepcopy
from urllib.parse import quote_plus
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, Response, abort
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("SITE_DATA_DIR") or (BASE / "data"))
UPLOADS = DATA / "uploads"
SEEDS = DATA / "seed_assets"
CONTENT_FILE = DATA / "site_content.json"

IMAGE_EXT = {"png","jpg","jpeg","webp"}
IMAGE_MIME = {"image/png","image/jpeg","image/webp"}
VIDEO_EXT = {"mp4","webm","mov"}
VIDEO_MIME = {"video/mp4","video/webm","video/quicktime"}

app = Flask(__name__)
app.secret_key = os.environ.get("SITE_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=120 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

DEFAULT_CONTENT = {
    "brand":{"name":"BodyMind Aerial Studio","tagline":"Danza aerea, tecnica ed emozione","city":"Aprilia (LT)"},
    "hero":{
        "eyebrow":"BODYMIND AERIAL STUDIO · APRILIA",
        "title":"Il corpo sale. La mente si libera.",
        "text":"Danza aerea ad Aprilia: tecnica, forza, espressione e consapevolezza. Percorsi per bambine, ragazze e adulte.",
        "cta":"Prenota una prova",
        "image":"",
        "video_file":"",
        "video_url":"https://www.instagram.com/reel/DdWNf0_NJ41/"
    },
    "courses":[
        {"title":"Danza Aerea","text":"Tessuti e cerchio: tecnica, forza, mobilità e qualità del movimento, dal primo approccio alle sequenze più evolute."},
        {"title":"Kids & Junior","text":"Un percorso dedicato alle più giovani per crescere in sicurezza, sviluppando coordinazione, fiducia e creatività."},
        {"title":"Performance","text":"Lavoro avanzato su presenza scenica, fluidità, combinazioni e costruzione coreografica per esibizioni e obiettivi sportivi."}
    ],
    "videos":[
        {"title":"BodyMind in movimento","subtitle":"Un assaggio del nostro lavoro in aria","url":"https://www.instagram.com/reel/DdWNf0_NJ41/"},
        {"title":"Kids & Junior","subtitle":"Crescere in aria con tecnica, fiducia e creatività","url":"https://www.instagram.com/reel/Da3EnTHN16f/"},
        {"title":"Tecnica e performance","subtitle":"Controllo, linee, presenza e costruzione scenica","url":"https://www.instagram.com/reel/DZSACDftK8u/"},
        {"title":"Dentro BodyMind","subtitle":"Allenamento, atmosfera e vita dello studio","url":"https://www.instagram.com/reel/DdLuWlqtx1i/"}
    ],
    "venues":[
        {
            "name":"Palagym Aprilia",
            "address":"Via della Meccanica, Aprilia (LT)",
            "course":"Danza Aerea · Junior · Adulte",
            "days":"Lunedì e mercoledì",
            "time":"18:00–21:30",
            "note":"Le fasce vengono organizzate in base a livello e disponibilità."
        },
        {
            "name":"Pianeta Forma",
            "address":"Via Aldo Moro 94/98, Aprilia (LT)",
            "course":"Kids & Junior",
            "days":"Martedì e giovedì",
            "time":"",
            "note":"Contattaci per l’orario aggiornato del gruppo Kids & Junior."
        }
    ],
    "about":{
        "title":"BodyMind",
        "text":"Corpo e mente non sono due parti separate del movimento. BodyMind unisce preparazione atletica, tecnica aerea, espressione e consapevolezza in un ambiente professionale, intenso e accogliente."
    },
    "contact":{"instagram":"@bodymind.aerialstudio","email":"","phone":"","whatsapp":"","address":"Aprilia (LT)"},
    "links":{"app":"https://app.bodymindaerialstudio.life","family":"https://app.bodymindaerialstudio.life/area-famiglie"},
    "visuals":{
        "logo":"/seed-media/logo?v=7",
        "hero_fallback":"/seed-media/gallery4?v=7",
        "location_photo":"/seed-media/gallery3?v=7",
        "gallery":[f"/seed-media/gallery{i}?v=7" for i in range(1,7)]
    },
    "seo":{
        "title":"BodyMind Aerial Studio | Danza Aerea ad Aprilia",
        "description":"BodyMind Aerial Studio ad Aprilia: danza aerea, tessuti, cerchio, corsi Kids & Junior e percorsi performance."
    },
    "_design_version":10,
}

SEED_SOURCES = {
    "logo":"https://app.bodymindaerialstudio.life/bodymind-media/logo",
    "gallery1":"https://app.bodymindaerialstudio.life/bodymind-media/family_cover",
    "gallery2":"https://app.bodymindaerialstudio.life/bodymind-media/gallery_1",
    "gallery3":"https://app.bodymindaerialstudio.life/bodymind-media/gallery_2",
    "gallery4":"https://app.bodymindaerialstudio.life/bodymind-media/gallery_3",
    "gallery5":"https://app.bodymindaerialstudio.life/static/bodymind/hero.jpg",
    "gallery6":"https://app.bodymindaerialstudio.life/static/bodymind/sunset.jpg",
}

def ensure_data():
    DATA.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    SEEDS.mkdir(parents=True, exist_ok=True)
    if not CONTENT_FILE.exists():
        CONTENT_FILE.write_text(json.dumps(DEFAULT_CONTENT, ensure_ascii=False, indent=2), encoding="utf-8")

def merge_defaults(defaults, value):
    if isinstance(defaults, dict):
        src = value if isinstance(value, dict) else {}
        return {k:merge_defaults(v, src.get(k)) for k,v in defaults.items()} | {k:deepcopy(v) for k,v in src.items() if k not in defaults}
    if isinstance(defaults, list):
        return value if isinstance(value, list) and value else deepcopy(defaults)
    return defaults if value is None else value

def save_content(content):
    ensure_data()
    tmp = CONTENT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONTENT_FILE)

def load_content():
    ensure_data()
    try:
        raw = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    c = merge_defaults(DEFAULT_CONTENT, raw)
    if int(c.get("_design_version", 0) or 0) < 9:
        c.setdefault("hero", {})
        c["hero"]["video_url"] = c["hero"].get("video_url") or DEFAULT_CONTENT["hero"]["video_url"]
        c["hero"]["video_file"] = c["hero"].get("video_file") or ""
        c["videos"] = deepcopy(DEFAULT_CONTENT["videos"])
        c["venues"] = deepcopy(DEFAULT_CONTENT["venues"])
        c.setdefault("visuals", {})
        if not c["visuals"].get("hero_fallback"):
            c["visuals"]["hero_fallback"] = DEFAULT_CONTENT["visuals"]["hero_fallback"]
        c["_design_version"] = 9
        save_content(c)
    return c

def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token
app.jinja_env.globals["csrf_token"] = csrf_token

def instagram_embed(url):
    if not isinstance(url, str):
        return ""
    m = re.search(r"https?://(?:www\.)?instagram\.com/(?:reel|p)/([^/?#]+)", url.strip(), re.I)
    if not m:
        return ""
    return f"https://www.instagram.com/reel/{m.group(1)}/embed/"
app.jinja_env.globals["instagram_embed"] = instagram_embed

def maps_url(address):
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(address or "")
app.jinja_env.globals["maps_url"] = maps_url

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("site_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def _seed_paths(slot):
    return SEEDS / f"{slot}.bin", SEEDS / f"{slot}.json"

def _download_seed(slot):
    if slot not in SEED_SOURCES:
        return None
    ensure_data()
    data_path, meta_path = _seed_paths(slot)
    if data_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return data_path, meta.get("content_type","image/jpeg")
        except Exception:
            pass
    try:
        req = urllib.request.Request(SEED_SOURCES[slot], headers={"User-Agent":"BodyMind-Site/7.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            ctype = (r.headers.get_content_type() or "").lower()
            if ctype not in IMAGE_MIME:
                raise ValueError("seed content-type non valido")
            payload = r.read(8 * 1024 * 1024 + 1)
            if not payload or len(payload) > 8 * 1024 * 1024:
                raise ValueError("seed size non valida")
        tmp = data_path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        tmp.replace(data_path)
        meta_path.write_text(json.dumps({"content_type":ctype,"source":SEED_SOURCES[slot]}), encoding="utf-8")
        return data_path, ctype
    except Exception as exc:
        app.logger.warning("seed %s unavailable: %s", slot, exc)
        return None

def _store_upload(storage, prefix, kind="image"):
    if not storage or not storage.filename:
        return None
    ext = storage.filename.rsplit(".",1)[-1].lower() if "." in storage.filename else ""
    mime = (storage.mimetype or "").lower()
    allowed_ext = IMAGE_EXT if kind == "image" else VIDEO_EXT
    allowed_mime = IMAGE_MIME if kind == "image" else VIDEO_MIME
    if ext not in allowed_ext or mime not in allowed_mime:
        expected = "JPG, PNG o WEBP" if kind == "image" else "MP4, WEBM o MOV"
        raise ValueError(f"File non valido. Usa {expected}.")
    final = f"{prefix}_{secrets.token_hex(8)}.{ext}"
    storage.save(UPLOADS / final)
    return f"/site-media/{final}"

def delete_owned_media(url):
    if not isinstance(url, str) or not url.startswith("/site-media/"):
        return
    name = secure_filename(url.rsplit("/",1)[-1])
    p = UPLOADS / name
    try:
        if p.exists() and p.is_file():
            p.unlink()
    except OSError:
        pass

@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options","nosniff")
    resp.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options","SAMEORIGIN")
    resp.headers.setdefault("Permissions-Policy","geolocation=(), microphone=(), camera=()")
    resp.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
    if request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.path.startswith("/site-media/") or request.path.startswith("/seed-media/"):
        resp.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
    elif request.path.startswith("/studio-admin"):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    else:
        resp.headers.setdefault("Cache-Control","no-store")
    resp.headers["X-BodyMind-Site"] = "v11-fullscreen"
    return resp

@app.get("/")
def home():
    return render_template("index.html", c=load_content())

@app.get("/seed-media/<slot>")
def seed_media(slot):
    got = _download_seed(slot)
    if not got:
        abort(404)
    path, ctype = got
    return send_from_directory(path.parent, path.name, mimetype=ctype, max_age=604800, conditional=True)

@app.get("/site-media/<path:name>")
def site_media(name):
    return send_from_directory(UPLOADS, secure_filename(name), max_age=604800, conditional=True)

@app.get("/favicon.ico")
def favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#050507"/><circle cx="32" cy="32" r="22" fill="none" stroke="#e8dce5" stroke-width="2"/><text x="32" y="39" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" font-weight="700" fill="white">BM</text></svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control":"public, max-age=86400"})

@app.get("/apple-touch-icon.png")
@app.get("/apple-touch-icon-precomposed.png")
@app.get("/apple-touch-icon-240x240.png")
@app.get("/apple-touch-icon-240x240-precomposed.png")
def apple_touch_icon():
    return seed_media("logo")

@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nAllow: /\nDisallow: /studio-admin\nSitemap: https://bodymindaerialstudio.life/sitemap.xml\n", mimetype="text/plain")

@app.get("/sitemap.xml")
def sitemap():
    return Response("""<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://bodymindaerialstudio.life/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url></urlset>""", mimetype="application/xml")

@app.route("/studio-admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("csrf") != session.get("_csrf"):
            return "CSRF non valido", 400
        expected_user = os.environ.get("SITE_ADMIN_USER","Dan2478")
        expected = os.environ.get("SITE_ADMIN_PASSWORD","")
        if not expected:
            flash("Password amministratore non configurata sul server.","error")
        elif secrets.compare_digest(request.form.get("username",""), expected_user) and secrets.compare_digest(request.form.get("password",""), expected):
            session.clear()
            session["site_admin"] = True
            csrf_token()
            return redirect(url_for("admin"))
        else:
            flash("Password non corretta.","error")
    return render_template("login.html")

@app.post("/studio-admin/logout")
@admin_required
def admin_logout():
    if request.form.get("csrf") != session.get("_csrf"):
        return "CSRF non valido", 400
    session.clear()
    return redirect(url_for("home"))

@app.route("/studio-admin", methods=["GET","POST"])
@admin_required
def admin():
    c = load_content()
    if request.method == "POST":
        if request.form.get("csrf") != session.get("_csrf"):
            return "CSRF non valido", 400

        groups = {
            "brand":["name","tagline","city"],
            "hero":["eyebrow","title","text","cta","video_url"],
            "about":["title","text"],
            "contact":["instagram","email","phone","whatsapp","address"],
            "links":["app","family"],
            "seo":["title","description"],
        }
        for group, fields in groups.items():
            c.setdefault(group,{})
            for field in fields:
                c[group][field] = request.form.get(f"{group}.{field}","").strip()

        c["courses"] = [
            {"title":request.form.get(f"course_{i}_title","").strip(),"text":request.form.get(f"course_{i}_text","").strip()}
            for i in range(3)
        ]

        c["videos"] = [
            {
                "title":request.form.get(f"video_{i}_title","").strip(),
                "subtitle":request.form.get(f"video_{i}_subtitle","").strip(),
                "url":request.form.get(f"video_{i}_url","").strip()
            }
            for i in range(4)
        ]

        c["venues"] = [
            {
                "name":request.form.get(f"venue_{i}_name","").strip(),
                "address":request.form.get(f"venue_{i}_address","").strip(),
                "course":request.form.get(f"venue_{i}_course","").strip(),
                "days":request.form.get(f"venue_{i}_days","").strip(),
                "time":request.form.get(f"venue_{i}_time","").strip(),
                "note":request.form.get(f"venue_{i}_note","").strip(),
            }
            for i in range(4)
            if request.form.get(f"venue_{i}_name","").strip()
        ]

        try:
            hero_image = _store_upload(request.files.get("hero_image"),"hero","image")
            if hero_image:
                delete_owned_media(c.setdefault("hero",{}).get("image",""))
                c["hero"]["image"] = hero_image

            hero_video = _store_upload(request.files.get("hero_video_file"),"hero_video","video")
            if hero_video:
                delete_owned_media(c.setdefault("hero",{}).get("video_file",""))
                c["hero"]["video_file"] = hero_video

            if request.form.get("remove_hero_video") == "1":
                delete_owned_media(c.setdefault("hero",{}).get("video_file",""))
                c["hero"]["video_file"] = ""

            logo = _store_upload(request.files.get("logo_image"),"logo","image")
            if logo:
                delete_owned_media(c.setdefault("visuals",{}).get("logo",""))
                c["visuals"]["logo"] = logo

            c.setdefault("visuals",{}).setdefault("gallery",deepcopy(DEFAULT_CONTENT["visuals"]["gallery"]))
            while len(c["visuals"]["gallery"]) < 6:
                c["visuals"]["gallery"].append(DEFAULT_CONTENT["visuals"]["gallery"][len(c["visuals"]["gallery"])])
            for i in range(6):
                img = _store_upload(request.files.get(f"gallery_image_{i}"), f"gallery_{i+1}", "image")
                if img:
                    delete_owned_media(c["visuals"]["gallery"][i])
                    c["visuals"]["gallery"][i] = img

            loc = _store_upload(request.files.get("location_image"),"location","image")
            if loc:
                delete_owned_media(c["visuals"].get("location_photo",""))
                c["visuals"]["location_photo"] = loc
        except ValueError as exc:
            flash(str(exc),"error")
            return render_template("admin.html", c=c)

        c["_design_version"] = 10
        save_content(c)
        flash("Sito aggiornato e pubblicato.","ok")
        return redirect(url_for("admin"))

    while len(c.get("venues",[])) < 4:
        c.setdefault("venues",[]).append({"name":"","address":"","course":"","days":"","time":"","note":""})
    while len(c.get("videos",[])) < 4:
        c.setdefault("videos",[]).append({"title":"","subtitle":"","url":""})
    return render_template("admin.html", c=c)

@app.get("/healthz")
def healthz():
    ensure_data()
    seeded = sum(1 for k in SEED_SOURCES if _seed_paths(k)[0].exists())
    return {"ok":True,"service":"bodymind-public-site","design":"v11-fullscreen","seeded_assets":seeded,"persistent_data":str(DATA)}, 200

if __name__ == "__main__":
    ensure_data()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8080")), debug=False)
