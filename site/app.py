import os, json, secrets
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("SITE_DATA_DIR") or (BASE / "data"))
UPLOADS = DATA / "uploads"
CONTENT_FILE = DATA / "site_content.json"
ALLOWED_EXT = {"png","jpg","jpeg","webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("SITE_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

DEFAULT_CONTENT = {
  "brand":{"name":"BodyMind Aerial Studio","tagline":"Danza aerea, tecnica ed emozione","city":"Aprilia (LT)"},
  "hero":{"eyebrow":"BODYMIND AERIAL STUDIO","title":"Il corpo sale. La mente si libera.","text":"Danza aerea per bambine, ragazze e adulte: tecnica, espressione e crescita in un ambiente strutturato e accogliente.","cta":"Scopri i corsi","image":""},
  "courses":[
    {"title":"Danza Aerea","text":"Tessuti e cerchio con percorsi progressivi per livello."},
    {"title":"Kids","text":"Percorsi dedicati alle più piccole, con tecnica, gioco e consapevolezza."},
    {"title":"Agonismo","text":"Preparazione avanzata per chi desidera un percorso più intenso e strutturato."}
  ],
  "schedule":{"title":"Orari","text":"Gli orari vengono aggiornati dalla segreteria BodyMind. Contattaci per conoscere disponibilità e livello più adatto."},
  "about":{"title":"BodyMind","text":"Un progetto dedicato alla danza aerea e alla crescita personale attraverso il movimento, la disciplina e l’espressione."},
  "contact":{"instagram":"@bodymind.aerialstudio","email":"","phone":"","whatsapp":"","address":"Via Antonio Gramsci 3, 04011 Aprilia (LT)"},
  "links":{"app":"https://app.bodymindaerialstudio.life","family":"https://app.bodymindaerialstudio.life/area-famiglie"},
  "seo":{"title":"BodyMind Aerial Studio | Danza Aerea ad Aprilia","description":"BodyMind Aerial Studio: danza aerea, tessuti, cerchio, corsi kids e percorsi agonistici ad Aprilia."}
}

def ensure_data():
    DATA.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if not CONTENT_FILE.exists():
        CONTENT_FILE.write_text(json.dumps(DEFAULT_CONTENT, ensure_ascii=False, indent=2), encoding="utf-8")

def load_content():
    ensure_data()
    try:
        return json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONTENT

def save_content(content):
    ensure_data()
    tmp = CONTENT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONTENT_FILE)

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
            "brand":["name","tagline","city"], "hero":["eyebrow","title","text","cta"],
            "schedule":["title","text"], "about":["title","text"],
            "contact":["instagram","email","phone","whatsapp","address"],
            "links":["app","family"], "seo":["title","description"]
        }
        for group, fields in groups.items():
            c.setdefault(group,{})
            for field in fields:
                c[group][field] = request.form.get(f"{group}.{field}","").strip()
        c["courses"] = [
            {"title":request.form.get(f"course_{i}_title","").strip(),
             "text":request.form.get(f"course_{i}_text","").strip()}
            for i in range(3)
        ]
        image = request.files.get("hero_image")
        if image and image.filename:
            ext = image.filename.rsplit(".",1)[-1].lower() if "." in image.filename else ""
            if ext not in ALLOWED_EXT:
                flash("Immagine non valida. Usa JPG, PNG o WEBP.", "error")
                return render_template("admin.html", c=c)
            final = f"hero_{secrets.token_hex(5)}.{ext}"
            image.save(UPLOADS / final)
            c.setdefault("hero",{})["image"] = f"/site-media/{final}"
        save_content(c)
        flash("Sito aggiornato.", "ok")
        return redirect(url_for("admin"))
    return render_template("admin.html", c=c)

@app.get("/healthz")
def healthz():
    return {"ok":True,"service":"bodymind-public-site"}, 200

if __name__ == "__main__":
    ensure_data()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8080")), debug=False)
