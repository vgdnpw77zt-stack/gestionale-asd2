from __future__ import annotations
import re
from datetime import date, datetime

_ODD={
 "0":1,"1":0,"2":5,"3":7,"4":9,"5":13,"6":15,"7":17,"8":19,"9":21,
 "A":1,"B":0,"C":5,"D":7,"E":9,"F":13,"G":15,"H":17,"I":19,"J":21,
 "K":2,"L":4,"M":18,"N":20,"O":11,"P":3,"Q":6,"R":8,"S":12,"T":14,
 "U":16,"V":10,"W":22,"X":25,"Y":24,"Z":23,
}
_EVEN={str(i):i for i in range(10)}
_EVEN.update({chr(ord("A")+i):i for i in range(26)})

def norm_cf(value):
    return re.sub(r"[^A-Z0-9]","",str(value or "").upper())

def valid_italian_cf(value):
    cf=norm_cf(value)
    if len(cf)!=16 or not re.fullmatch(r"[A-Z0-9]{16}",cf):
        return False
    try:
        total=0
        for idx,ch in enumerate(cf[:15],start=1):
            total += _ODD[ch] if idx%2==1 else _EVEN[ch]
        return chr(ord("A")+(total%26))==cf[-1]
    except Exception:
        return False

def iso_date(value):
    raw=str(value or "").strip()
    if not raw:
        return ""
    raw=raw[:10]
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%d.%m.%Y"):
        try:
            return datetime.strptime(raw,fmt).date().isoformat()
        except Exception:
            pass
    return ""

def age_from_birth(value, today=None):
    d=iso_date(value)
    if not d:
        return None
    born=date.fromisoformat(d); today=today or date.today()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day))

def cf_birth_date_consistent(value,birth_value):
    cf=norm_cf(value)
    birth=iso_date(birth_value)
    if not valid_italian_cf(cf) or not birth:
        return False
    try:
        d=date.fromisoformat(birth)
        months={"A":1,"B":2,"C":3,"D":4,"E":5,"H":6,"L":7,"M":8,"P":9,"R":10,"S":11,"T":12}
        yy=int(cf[6:8]); mm=months.get(cf[8]); dd=int(cf[9:11]); day=dd-40 if dd>40 else dd
        return yy==(d.year%100) and mm==d.month and day==d.day
    except Exception:
        return False

def enrollment_identity_ready(analysis, require_valid_cf=False):
    a=analysis if isinstance(analysis,dict) else {}
    first=str(a.get("first_name") or "").strip()
    last=str(a.get("last_name") or "").strip()
    birth=iso_date(a.get("birth_date"))
    cf=norm_cf(a.get("codice_fiscale"))
    try: conf=float(a.get("confidence") or 0)
    except Exception: conf=0.0
    if str(a.get("document_type") or "")!="modulo_unico_tesseramento":
        return False
    if not first or not last:
        return False
    cf_valid=valid_italian_cf(cf)
    cf_birth_ok=bool(cf_valid and birth and cf_birth_date_consistent(cf,birth))
    # High-confidence MU + valid CF is sufficient. For a slightly lower semantic
    # score, require the stronger checksum + DOB consistency rather than manual assignment.
    if require_valid_cf:
        if not cf_valid:
            return False
        return conf>=.95 or (conf>=.90 and cf_birth_ok)
    return (conf>=.95 and (cf_valid or bool(birth))) or (conf>=.90 and cf_birth_ok)

def find_existing_athlete(conn,analysis):
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(tesserati)").fetchall()}
    a=analysis if isinstance(analysis,dict) else {}
    cf=norm_cf(a.get("codice_fiscale"))
    if cf and "codice_fiscale" in cols:
        rows=conn.execute(
            "SELECT * FROM tesserati WHERE upper(replace(replace(coalesce(codice_fiscale,''),' ',''),'-',''))=?",
            (cf,)
        ).fetchall()
        if len(rows)==1:
            return rows[0],"codice_fiscale"
    first=str(a.get("first_name") or "").strip()
    last=str(a.get("last_name") or "").strip()
    birth=iso_date(a.get("birth_date"))
    if first and last and {"nome","cognome"}.issubset(cols):
        sql="SELECT * FROM tesserati WHERE lower(trim(coalesce(nome,'')))=lower(?) AND lower(trim(coalesce(cognome,'')))=lower(?)"
        vals=[first,last]
        if birth and "data_nascita" in cols:
            sql+=" AND substr(coalesce(data_nascita,''),1,10)=?"
            vals.append(birth)
        rows=conn.execute(sql,tuple(vals)).fetchall()
        if len(rows)==1:
            return rows[0],"nome_cognome_data_nascita" if birth else "nome_cognome"
    return None,""

def residence_from_analysis(analysis):
    a=analysis if isinstance(analysis,dict) else {}
    city=str(a.get("city") or "").strip()
    province=str(a.get("province") or "").strip().upper()
    postal=str(a.get("postal_code") or "").strip()
    if not city and not province and not postal:
        return ""
    loc=" ".join(x for x in (postal,city) if x).strip()
    if province:
        return (loc+" ("+province+")").strip() if loc else province
    return loc

def athlete_fields_from_analysis(conn,analysis):
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(tesserati)").fetchall()}
    a=analysis if isinstance(analysis,dict) else {}
    birth=iso_date(a.get("birth_date"))
    age=age_from_birth(birth)
    data={
      "nome":str(a.get("first_name") or "").strip(),
      "cognome":str(a.get("last_name") or "").strip(),
      "codice_fiscale":norm_cf(a.get("codice_fiscale")),
      "data_nascita":birth,
      "luogo_nascita":str(a.get("birth_place") or "").strip(),
      "indirizzo":str(a.get("address") or "").strip(),
      "residenza":residence_from_analysis(a),
      "citta":str(a.get("city") or "").strip(),
      "comune":str(a.get("city") or "").strip(),
      "cap":str(a.get("postal_code") or "").strip(),
      "provincia":str(a.get("province") or "").strip(),
      "telefono":str(a.get("phone") or "").strip(),
      "cellulare":str(a.get("phone") or "").strip(),
      "email":str(a.get("email") or "").strip(),
      "genitore":str(a.get("guardian_name") or "").strip(),
      "nome_genitore":str(a.get("guardian_name") or "").strip(),
      "telefono_genitore":str(a.get("guardian_phone") or "").strip(),
      "email_genitore":str(a.get("guardian_email") or "").strip(),
      "nazionalita":str(a.get("nationality") or "").strip(),
      "sesso":str(a.get("gender") or "").strip(),
      "note":str(a.get("notes") or "").strip(),
      "attivo":1,
      "minorenne":1 if age is not None and age<18 else 0,
      "created_at":datetime.now().isoformat(timespec="seconds"),
      "updated_at":datetime.now().isoformat(timespec="seconds"),
    }
    # Keep only columns actually present and non-empty, except booleans/defaults.
    out={}
    for k,v in data.items():
        if k not in cols:
            continue
        if v in ("",None) and k not in ("attivo","minorenne"):
            continue
        out[k]=v
    return out

def create_athlete_from_analysis(conn,analysis,source="documento",require_valid_cf=False):
    existing,reason=find_existing_athlete(conn,analysis)
    if existing:
        return {"created":False,"existing":True,"tesserato_id":int(existing["id"]),"reason":reason}
    if not enrollment_identity_ready(analysis,require_valid_cf=require_valid_cf):
        return {"created":False,"existing":False,"tesserato_id":None,"reason":"identita_non_sufficientemente_certa"}
    fields=athlete_fields_from_analysis(conn,analysis)
    if not fields.get("nome") or not fields.get("cognome"):
        return {"created":False,"existing":False,"tesserato_id":None,"reason":"nome_cognome_mancanti"}

    info=conn.execute("PRAGMA table_info(tesserati)").fetchall()
    for r in info:
        col=str(r[1]); typ=str(r[2] or "").upper(); notnull=bool(r[3]); default=r[4]; pk=bool(r[5])
        if pk or col in fields or not notnull or default is not None:
            continue
        if col=="attivo":
            fields[col]=1
        elif col in ("created_at","updated_at"):
            fields[col]=datetime.now().isoformat(timespec="seconds")
        elif any(x in typ for x in ("INT","REAL","NUM","DEC","FLOAT","DOUBLE")):
            fields[col]=0
        else:
            fields[col]=""
    cols=list(fields.keys())
    vals=[fields[k] for k in cols]
    cur=conn.execute("INSERT INTO tesserati ("+",".join(cols)+") VALUES ("+",".join("?" for _ in cols)+")",tuple(vals))
    tid=int(cur.lastrowid)

    # Preserve guardian contacts in the minor table when compatible columns exist.
    age=age_from_birth(analysis.get("birth_date") if isinstance(analysis,dict) else "")
    if age is not None and age<18:
        tables={str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "minori" in tables:
            mcols={str(r[1]) for r in conn.execute("PRAGMA table_info(minori)").fetchall()}
            if "tesserato_id" in mcols:
                existing_minor=conn.execute("SELECT 1 FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
                if not existing_minor:
                    mf={"tesserato_id":tid}
                    amap={
                      "genitore":"guardian_name","nome_genitore":"guardian_name",
                      "telefono_genitore":"guardian_phone","email_genitore":"guardian_email"
                    }
                    for col,key in amap.items():
                        val=str((analysis or {}).get(key) or "").strip()
                        if col in mcols and val:
                            mf[col]=val
                    try:
                        conn.execute("INSERT INTO minori ("+",".join(mf.keys())+") VALUES ("+",".join("?" for _ in mf)+")",tuple(mf.values()))
                    except Exception:
                        pass
    return {"created":True,"existing":False,"tesserato_id":tid,"reason":"creato_da_"+str(source),"fields":fields}
