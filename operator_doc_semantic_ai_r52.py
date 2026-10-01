from __future__ import annotations
import base64, json, mimetypes, os, re
from pathlib import Path
from .operator_doc_semantic_core_r52 import DOC_TYPES, semantic_key, sha256_bytes

SEMANTIC_SCHEMA={
 "type":"object","additionalProperties":False,
 "properties":{
  "document_type":{"type":"string","enum":list(DOC_TYPES)},
  "person_name":{"type":"string"},"codice_fiscale":{"type":"string"},
  "birth_date":{"type":"string"},"issue_date":{"type":"string"},"expiry_date":{"type":"string"},
  "season_year":{"type":"string"},"form_version":{"type":"string"},
  "guardian_name":{"type":"string"},"doctor_name":{"type":"string"},
  "privacy_consent":{"type":"string","enum":["yes","no","unknown"]},
  "image_consent":{"type":"string","enum":["yes","no","unknown"]},
  "autonomous_exit":{"type":"string","enum":["yes","no","unknown"]},
  "delegation":{"type":"string","enum":["yes","no","unknown"]},
  "athlete_signature":{"type":"string","enum":["yes","no","unknown"]},
  "guardian_signature":{"type":"string","enum":["yes","no","unknown"]},
  "content_summary":{"type":"string"},"evidence":{"type":"array","items":{"type":"string"}},
  "confidence":{"type":"number","minimum":0,"maximum":1}
 },
 "required":["document_type","person_name","codice_fiscale","birth_date","issue_date","expiry_date",
             "season_year","form_version","guardian_name","doctor_name","privacy_consent","image_consent",
             "autonomous_exit","delegation","athlete_signature","guardian_signature","content_summary",
             "evidence","confidence"]
}
COMPARE_SCHEMA={
 "type":"object","additionalProperties":False,
 "properties":{
  "same_document":{"type":"boolean"},"confidence":{"type":"number","minimum":0,"maximum":1},
  "reason":{"type":"string"},"material_differences":{"type":"array","items":{"type":"string"}}
 },
 "required":["same_document","confidence","reason","material_differences"]
}

def _parse_json(raw):
    s=str(raw or "").strip()
    if s.startswith("```"):
        s=re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$","",s,flags=re.I|re.S).strip()
    try:
        obj=json.loads(s)
        if isinstance(obj,dict): return obj
    except Exception:
        pass
    dec=json.JSONDecoder()
    for i,ch in enumerate(s):
        if ch!="{":
            continue
        try:
            obj,_end=dec.raw_decode(s[i:])
            if isinstance(obj,dict):
                return obj
        except Exception:
            continue
    raise RuntimeError("Risposta IA documentale non interpretabile")

def _response_text(response):
    raw=str(getattr(response,"output_text","") or "").strip()
    if raw:
        return raw
    parts=[]
    try:
        for item in (getattr(response,"output",None) or []):
            for part in (getattr(item,"content",None) or []):
                if str(getattr(part,"type","") or "")=="output_text":
                    txt=str(getattr(part,"text","") or "")
                    if txt:
                        parts.append(txt)
    except Exception:
        pass
    return "\n".join(parts).strip()

def _input_part(name,data):
    if not data or len(data)>18*1024*1024: return None
    ext=Path(str(name or "")).suffix.lower()
    encoded=base64.b64encode(data).decode("ascii")
    if ext in {".png",".jpg",".jpeg",".webp"}:
        mime=mimetypes.guess_type(str(name or ""))[0] or "image/jpeg"
        return {"type":"input_image","image_url":"data:"+mime+";base64,"+encoded,"detail":"high"}
    if ext==".pdf":
        return {"type":"input_file","filename":str(name or "documento.pdf"),"file_data":"data:application/pdf;base64,"+encoded,"detail":"high"}
    return None

def _call_json(conn,model,prompt,parts,schema,name,record_usage,max_tokens):
    from openai import OpenAI
    client=OpenAI(api_key=str(os.environ.get("OPENAI_API_KEY") or "").strip(),timeout=45.0,max_retries=0)
    msg={"role":"user","content":[{"type":"input_text","text":prompt}]+list(parts or [])}
    kwargs={"model":model,"input":[msg],"reasoning":{"effort":"none"},"max_output_tokens":int(max_tokens),"store":False}
    try:
        response=client.responses.create(**kwargs,text={"format":{"type":"json_schema","name":name,"strict":True,"schema":schema}})
    except Exception:
        msg["content"][0]["text"]=prompt+"\nRestituisci solo JSON valido conforme allo schema: "+json.dumps(schema,ensure_ascii=False)
        response=client.responses.create(**kwargs)
    if record_usage: record_usage(conn,response,model)
    return _parse_json(_response_text(response))

def analyze_bytes(conn,name,data,extracted_text="",type_hint="",record_usage=None):
    model=str(os.environ.get("BODYMIND_AI_DOCUMENT_MODEL") or os.environ.get("BODYMIND_AI_MODEL") or "gpt-6-luna").strip()
    prompt=(
      "Analizza questo documento reale della segreteria BodyMind Aerial Studio ASD. "
      "Leggi testo, compilazioni, date, checkbox, firme e annotazioni visibili. "
      "Non identificare la persona dal solo nome file se il contenuto dice altro. "
      "Per Modulo Unico valuta anche consensi, autorizzazioni, firme e stagione/versione. "
      "Se nel CONTENUTO compare esplicitamente Modulo Unico, modulo di iscrizione/tesseramento, domanda di iscrizione con consensi/manleva, "
      "classificalo come modulo_unico_tesseramento con confidenza alta se intestatario e struttura sono coerenti. "
      "Per certificato medico valuta intestatario, rilascio, scadenza e medico. "
      "Modulo Unico e certificato medico sono tipi distinti: non confonderli mai. "
      "Usa stringa vuota se un dato non è leggibile e unknown per scelte non determinabili."
      +(("\nTipo dichiarato dall'utente, da verificare: "+str(type_hint)) if type_hint else "")
      +(("\nTesto estratto localmente:\n"+str(extracted_text)[:18000]) if extracted_text else "")
    )
    part=_input_part(name,data)
    cb=(lambda c,r,m: record_usage(c,r,m,"document_semantics")) if record_usage else None
    obj=_call_json(conn,model,prompt,[part] if part else [],SEMANTIC_SCHEMA,"bodymind_doc_semantics",cb,950)
    dtype=str(obj.get("document_type") or "altro")
    obj["document_type"]=dtype if dtype in DOC_TYPES else "altro"
    try: obj["confidence"]=max(0.0,min(1.0,float(obj.get("confidence") or 0)))
    except Exception: obj["confidence"]=0.0
    obj["semantic_key"]=semantic_key(obj); obj["sha256"]=sha256_bytes(data); obj["model"]=model
    return obj

def compare_bytes(conn,name_a,data_a,analysis_a,name_b,data_b,analysis_b,record_usage=None):
    if sha256_bytes(data_a)==sha256_bytes(data_b):
        return {"same_document":True,"confidence":1.0,"reason":"Contenuto binario identico.","material_differences":[],"method":"sha256"}
    model=str(os.environ.get("BODYMIND_AI_DOCUMENT_STRONG_MODEL") or "gpt-6-sol").strip()
    prompt=(
      "Confronta materialmente Documento A e Documento B. Decidi se sono la stessa copia/logico documento "
      "oppure versioni/documenti distinti. Controlla persona, date, versione/stagione, checkbox, consensi, "
      "firme, annotazioni e contenuto manoscritto. Una differenza sostanziale rende i documenti distinti. "
      "same_document=true solo con evidenza forte; in dubbio false. "
      "REGOLA ASSOLUTA: se document_type di A e B è diverso, soprattutto modulo_unico_tesseramento vs certificato_medico, same_document deve essere false."
      "\nMetadati A: "+json.dumps(analysis_a or {},ensure_ascii=False)[:7000]+
      "\nMetadati B: "+json.dumps(analysis_b or {},ensure_ascii=False)[:7000]
    )
    parts=[{"type":"input_text","text":"DOCUMENTO A"}]
    a=_input_part(name_a,data_a); b=_input_part(name_b,data_b)
    if a: parts.append(a)
    parts.append({"type":"input_text","text":"DOCUMENTO B"})
    if b: parts.append(b)
    cb=(lambda c,r,m: record_usage(c,r,m,"document_compare")) if record_usage else None
    obj=_call_json(conn,model,prompt,parts,COMPARE_SCHEMA,"bodymind_doc_compare",cb,650)
    try: obj["confidence"]=max(0.0,min(1.0,float(obj.get("confidence") or 0)))
    except Exception: obj["confidence"]=0.0
    obj["method"]="multimodal"; obj["model"]=model
    return obj
