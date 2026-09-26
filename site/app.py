import os, json, secrets
from pathlib import Path
from functools import wraps
from copy import deepcopy
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("SITE_DATA_DIR") or (BASE / "data"))
UPLOADS = DATA / "uploads"
CONTENT_FILE = DATA / "site_content.json"
ALLOWED_EXT = {"png","jpg","jpeg","webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("SITE_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

DEFAULT_CONTENT = {
  "brand":{"name":"BodyMind Aerial Studio","tagline":"Danza aerea, tecnica ed emozione","city":"Aprilia (LT)"},
  "hero":{
    "eyebrow":"BODYMIND AERIAL STUDIO · APRILIA",
    "title":"Il corpo sale. La mente si libera.",
    "text":"Danza aerea per bambine, ragazze e adulte. Tecnica, forza, espressione e libertà in un percorso costruito intorno alla persona.",
    "cta":"Scopri i corsi",
    "image":""
  },
  "courses":[
    {"title":"Danza Aerea","text":"Tessuti e cerchio: tecnica, forza, mobilità e qualità del movimento, dal primo approccio alle sequenze più evolute."},
    {"title":"Kids & Junior","text":"Un percorso dedicato alle più giovani per crescere in sicurezza, sviluppando coordinazione, fiducia e creatività."},
    {"title":"Performance","text":"Lavoro avanzato su presenza scenica, fluidità, combinazioni e costruzione coreografica per esibizioni e obiettivi sportivi."}
  ],
  "schedule":{
    "title":"Allenati con noi",
    "text":"Le lezioni si svolgono presso Palagym Aprilia. Contattaci per conoscere giorni, disponibilità e livello più adatto."
  },
  "about":{
    "title":"BodyMind",
    "text":"Corpo e mente non sono due parti separate del movimento. BodyMind nasce per unire preparazione atletica, tecnica aerea, espressione e consapevolezza in un ambiente professionale, intenso e accogliente."
  },
  "contact":{
    "instagram":"@bodymind.aerialstudio",
    "email":"",
    "phone":"",
    "whatsapp":"",
    "address":"Presso Palagym Aprilia · Via della Meccanica, Aprilia (LT)"
  },
  "links":{
    "app":"https://app.bodymindaerialstudio.life",
    "family":"https://app.bodymindaerialstudio.life/area-famiglie"
  },
  "visuals":{
    "logo":"https://app.bodymindaerialstudio.life/bodymind-media/logo",
    "hero_fallback":"https://app.bodymindaerialstudio.life/bodymind-media/mobile_cover",
    "gallery":[
      "https://app.bodymindaerialstudio.life/bodymind-media/family_cover",
      "https://app.bodymindaerialstudio.life/bodymind-media/mobile_cover",
      "https://app.bodymindaerialstudio.life/bodymind-media/gallery_1",
      "https://app.bodymindaerialstudio.life/bodymind-media/gallery_2"
    ]
  },
  "seo":{
    "title":"BodyMind Aerial Studio | Danza Aerea ad Aprilia",
    "description":"BodyMind Aerial Studio ad Aprilia: danza aerea, tessuti, cerchio, corsi Kids & Junior e percorsi performance presso Palagym Aprilia."
  }
}

def ensure_data():
    DATA.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if not CONTENT_FILE.exists():
        CONTENT_FILE.write_text(json.dumps(DEFAULT_CONTENT, ensure_ascii=False, indent=2), encoding="utf-8")

def merge_defaults(defaults, value):
    if isinstance(defaults, dict):
        src = value if isinstance(value, dict) else {}
        return {k: merge_defaults(v, src.get(k)) for k, v in defaults.items()} | {
            k: deepcopy(v) for k, v in src.items() if k not in defaults
        }
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
    changed = False
    try:
        raw = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    content = merge_defaults(DEFAULT_CONTENT, raw)

    # One-time migration from the original placeholder site to the premium BodyMind design.
    if int(content.get("_design_version", 0) or 0) < 3:
        content["hero"]["eyebrow"] = "BODYMIND AERIAL STUDIO · APRILIA"
        content["hero"]["text"] = "Danza aerea per bambine, ragazze e adulte. Tecnica, forza, espressione e libertà in un percorso costruito intorno alla persona."
        content["hero"]["image"] = ""
        content["courses"] = deepcopy(DEFAULT_CONTENT["courses"])
        content["schedule"] = deepcopy(DEFAULT_CONTENT["schedule"])
        content["about"] = deepcopy(DEFAULT_CONTENT["about"])
        content["contact"]["address"] = DEFAULT_CONTENT["contact"]["address"]
        content["seo"]["description"] = DEFAULT_CONTENT["seo"]["description"]
        content["_design_version"] = 3
        changed = True

    old_addresses = {
        "Via Antonio Gramsci 3, 04011 Aprilia (LT)",
        "Via Gramsci 3, 04011 Aprilia (LT)"
    }
    if content.get("contact", {}).get("address") in old_addresses:
        content["contact"]["address"] = DEFAULT_CONTENT["contact"]["address"]
        changed = True
    if changed:
        save_content(content)
    return content

def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        session["_csrf"] = token
    return token

app.jinja_env.globals["csrf_token"] = csrf_token

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("site_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def store_image(storage, prefix):
    if not storage or not storage.filename:
        return None
    ext = storage.filename.rsplit(".",1)[-1].lower() if "." in storage.filename else ""
    if ext not in ALLOWED_EXT:
        raise ValueError("Immagine non valida. Usa JPG, PNG o WEBP.")
    final = f"{prefix}_{secrets.token_hex(6)}.{ext}"
    storage.save(UPLOADS / final)
    return f"/site-media/{final}"

@app.get("/")
def home():
    return render_template("index.html", c=load_content())

@app.get("/site-media/<path:name>")
def site_media(name):
    return send_from_directory(UPLOADS, secure_filename(name))

@app.route("/studio-admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        expected = os.environ.get("SITE_ADMIN_PASSWORD","")
        if not expected:
            flash("Password amministratore non configurata sul server.", "error")
        elif secrets.compare_digest(request.form.get("password",""), expected):
            session["site_admin"] = True
            return redirect(url_for("admin"))
        else:
            flash("Password non corretta.", "error")
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
            "hero":["eyebrow","title","text","cta"],
            "schedule":["title","text"],
            "about":["title","text"],
            "contact":["instagram","email","phone","whatsapp","address"],
            "links":["app","family"],
            "seo":["title","description"]
        }
        for group, fields in groups.items():
            c.setdefault(group,{})
            for field in fields:
                c[group][field] = request.form.get(f"{group}.{field}","").strip()

        c["courses"] = [
            {
                "title":request.form.get(f"course_{i}_title","").strip(),
                "text":request.form.get(f"course_{i}_text","").strip()
            } for i in range(3)
        ]

        try:
            hero = store_image(request.files.get("hero_image"), "hero")
            if hero:
                c.setdefault("hero", {})["image"] = hero

            logo = store_image(request.files.get("logo_image"), "logo")
            if logo:
                c.setdefault("visuals", {})["logo"] = logo

            c.setdefault("visuals", {}).setdefault("gallery", list(DEFAULT_CONTENT["visuals"]["gallery"]))
            while len(c["visuals"]["gallery"]) < 4:
                c["visuals"]["gallery"].append(DEFAULT_CONTENT["visuals"]["gallery"][len(c["visuals"]["gallery"])])
            for i in range(4):
                img = store_image(request.files.get(f"gallery_image_{i}"), f"gallery_{i+1}")
                if img:
                    c["visuals"]["gallery"][i] = img
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("admin.html", c=c)

        save_content(c)
        flash("Sito aggiornato e pubblicato.", "ok")
        return redirect(url_for("admin"))
    return render_template("admin.html", c=c)

@app.get("/healthz")
def healthz():
    return {"ok":True,"service":"bodymind-public-site"}, 200

if __name__ == "__main__":
    ensure_data()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8080")), debug=False)
