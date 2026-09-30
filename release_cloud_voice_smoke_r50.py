# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from io import BytesIO
import json, os, re, sys

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_CLOUD_VOICE_SMOKE_R50B'
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if MARKER.exists():
    print('[cloud-voice-r50b-smoke] already attempted '+MARKER.read_text(encoding='utf-8',errors='replace')[:1800],flush=True)
else:
    outcome={
        'ok':False,
        'tts_model':str(os.environ.get('BODYMIND_TTS_MODEL') or ''),
        'tts_voice':str(os.environ.get('BODYMIND_TTS_VOICE') or ''),
        'stt_model':str(os.environ.get('BODYMIND_STT_MODEL') or ''),
        'audio_bytes':0,
        'transcript':'',
        'error':'',
    }
    try:
        os.chdir(str(APP))
        if str(APP) not in sys.path:
            sys.path.insert(0,str(APP))
        from asd_app.core import app
        import asd_app.routes_operator_bodymind  # register operator cloud voice routes
        with app.test_client() as client:
            with client.session_transaction() as s:
                s['logged']=True
                s['username']='admin'
                s['display_name']='Daniele'
                s['role']='admin'
                s['tenant_slug']='default'
                s['_csrf_token']='r50-voice-smoke'
            phrase='BodyMind segreteria pronta.'
            tts=client.post(
                '/operatore-bodymind/voice/speak',
                json={'text':phrase},
                headers={'X-CSRFToken':'r50-voice-smoke'}
            )
            if tts.status_code!=200:
                raise RuntimeError('TTS HTTP '+str(tts.status_code)+' '+tts.get_data(as_text=True)[:500])
            audio=tts.data or b''
            outcome['audio_bytes']=len(audio)
            if len(audio)<1000:
                raise RuntimeError('TTS returned too little audio')
            usage_id=str(tts.headers.get('X-BodyMind-Usage-Id') or '')
            data={
                'audio':(BytesIO(audio),'bodymind-smoke.mp3'),
                'duration_ms':'3000',
            }
            stt=client.post(
                '/operatore-bodymind/voice/transcribe',
                data=data,
                content_type='multipart/form-data',
                headers={'X-CSRFToken':'r50-voice-smoke'}
            )
            payload=stt.get_json(silent=True) or {}
            if stt.status_code!=200:
                raise RuntimeError('STT HTTP '+str(stt.status_code)+' '+str(payload)[:600])
            transcript=str(payload.get('text') or '').strip()
            outcome['transcript']=transcript[:500]
            norm=re.sub(r'[^a-z0-9]+','',transcript.lower())
            if 'bodymind' not in norm or 'pront' not in norm:
                raise RuntimeError('unexpected transcript '+repr(transcript))
            if usage_id:
                client.post(
                    '/operatore-bodymind/cloud/usage/tts',
                    json={'usage_id':usage_id,'seconds':3.0},
                    headers={'X-CSRFToken':'r50-voice-smoke'}
                )
            outcome['ok']=True
    except Exception as exc:
        outcome['error']=repr(exc)[:1800]
    MARKER.write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf-8')
    print('[cloud-voice-r50-smoke] '+json.dumps(outcome,ensure_ascii=False),flush=True)
