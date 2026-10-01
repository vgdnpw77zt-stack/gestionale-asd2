# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r59/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R59_VOICE_STATE_MACHINE' in s:
    print('[operator-r59] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R57.0-fast-safe-dedupe-avatar"','OPERATOR_VERSION = "R59.0-voice-state-fix"',1)

old='''      let cloudRecorder=null,cloudChunks=[],cloudRecording=false,cloudAudio=null,cloudMaxTimer=null,cloudRecordingStartedAt=0;
      let voiceAudioCtx=null,voicePlaybackSource=null,lastTtsBytes=null;
      let micAnalyser=null,micSourceNode=null,micLevelTimer=null,cloudSpeechSeen=false,cloudLastSpeechAt=0;'''
new='''      // BODYMIND_R59_VOICE_STATE_MACHINE
      let cloudRecorder=null,cloudChunks=[],cloudRecording=false,cloudAudio=null,cloudMaxTimer=null,cloudRecordingStartedAt=0;
      let voiceAudioCtx=null,voicePlaybackSource=null,lastTtsBytes=null;
      let micAnalyser=null,micSourceNode=null,micLevelTimer=null,cloudSpeechSeen=false,cloudLastSpeechAt=0;
      let consecutiveEmptyStt=0,voiceTranscribing=false;'''
if old not in s: raise RuntimeError('R59 voice vars anchor missing')
s=s.replace(old,new,1)

old='''      async function cloudStopAndTranscribe(){{
        if(!cloudRecording||!cloudRecorder)return;
        const elapsed=performance.now()-cloudRecordingStartedAt;
        if(elapsed<650){{if(voiceStatus)voiceStatus.textContent='Ti ascolto…';return}}
        cloudRecording=false;'''
new='''      async function cloudStopAndTranscribe(){{
        if(!cloudRecording||!cloudRecorder||voiceTranscribing)return;
        const elapsed=performance.now()-cloudRecordingStartedAt;
        if(elapsed<650){{if(voiceStatus)voiceStatus.textContent='Ti ascolto…';return}}
        cloudRecording=false;
        voiceTranscribing=true;'''
if old not in s: raise RuntimeError('R59 stop anchor missing')
s=s.replace(old,new,1)

old='''            const blob=new Blob(cloudChunks,{{type:cloudRecorder?.mimeType||mime||'audio/webm'}});
            if(blob.size<1000){{if(voiceStatus)voiceStatus.textContent='Non ho rilevato audio. Riprova.';return}}
            if(!cloudSpeechSeen){{
              const t='Il microfono è aperto, ma non rilevo la tua voce. Controlla il microfono e riprova.';
              if(voiceStatus)voiceStatus.textContent=t;
              if(voiceStageOpen)setVoiceStage('Non sento voce',t,'Parla più vicino al microfono o controlla il permesso audio.');
              voiceDiag('no_voice_signal',{{len:blob.size}});
              return;
            }}'''
new='''            const blob=new Blob(cloudChunks,{{type:cloudRecorder?.mimeType||mime||'audio/webm'}});
            if(blob.size<1000){{
              voiceTranscribing=false;
              if(voiceStatus)voiceStatus.textContent='Non ho rilevato audio.';
              if(voiceStageOpen)setVoiceStage('Non ho sentito nulla','Tocca per riprovare.','Il microfono è pronto.');
              return;
            }}
            if(!cloudSpeechSeen){{
              voiceTranscribing=false;
              consecutiveEmptyStt++;
              const t='Non ho rilevato una frase chiara.';
              if(voiceStatus)voiceStatus.textContent=t;
              if(voiceStageOpen)setVoiceStage('Non ho capito','Tocca per riprovare.','Non ho inviato nulla al gestionale.');
              voiceDiag('no_voice_signal',{{len:blob.size}});
              return;
            }}'''
if old not in s: raise RuntimeError('R59 no-audio anchor missing')
s=s.replace(old,new,1)

old='''              const r=await fetch('/operatore-bodymind/voice/transcribe',{{method:'POST',headers:{{'X-CSRFToken':csrf}},body:fd}});
              const d=await r.json();
              if(!r.ok)throw new Error(d.text||('STT HTTP '+r.status));
              input.value=String(d.text||'').trim();
              if(!input.value)throw new Error('Trascrizione vuota');
              if(voiceStatus)voiceStatus.textContent='Ho capito. Elaboro…';
              if(voiceStageOpen)setVoiceStage('Ho capito',input.value,'Ora controllo BodyMind.');
              await ask(input.value);
            }}catch(e){{
              const t=String(e?.message||e||'Trascrizione cloud non disponibile');
              if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot');
            }}'''
new='''              const r=await fetch('/operatore-bodymind/voice/transcribe',{{method:'POST',headers:{{'X-CSRFToken':csrf}},body:fd}});
              let d={{}};try{{d=await r.json()}}catch(_e){{}}
              if(r.status===422){{
                consecutiveEmptyStt++;
                voiceTranscribing=false;
                const t=String(d.text||'Non ho riconosciuto una frase.');
                if(voiceStatus)voiceStatus.textContent=t;
                if(voiceStageOpen)setVoiceStage('Non ho capito','Tocca per riprovare.','Non ho inviato nulla al gestionale.');
                voiceDiag('stt_empty',{{len:blob.size,message:t,attempt:consecutiveEmptyStt}});
                return;
              }}
              if(!r.ok)throw new Error(d.text||('STT HTTP '+r.status));
              input.value=String(d.text||'').trim();
              if(!input.value){{
                consecutiveEmptyStt++;
                voiceTranscribing=false;
                if(voiceStageOpen)setVoiceStage('Non ho capito','Tocca per riprovare.','Non ho inviato nulla al gestionale.');
                return;
              }}
              consecutiveEmptyStt=0;
              voiceTranscribing=false;
              if(voiceStatus)voiceStatus.textContent='Ho capito. Elaboro…';
              if(voiceStageOpen)setVoiceStage('Ho capito',input.value,'Ora controllo BodyMind.');
              await ask(input.value);
            }}catch(e){{
              voiceTranscribing=false;
              const t=String(e?.message||e||'Trascrizione cloud non disponibile');
              if(voiceStatus)voiceStatus.textContent=t;
              if(voiceStageOpen)setVoiceStage('Trascrizione interrotta','Tocca per riprovare.',t);
              addMsg(t,'bot');
            }}'''
if old not in s: raise RuntimeError('R59 STT catch anchor missing')
s=s.replace(old,new,1)

# Guard against stale transcribing state when opening mic manually.
old='''      async function cloudStartMic(ev){{
        if(ev){{ev.preventDefault();ev.stopImmediatePropagation()}}
        if(!voiceStageOpen)openVoiceStage();
        if(cloudRecording){{await cloudStopAndTranscribe();return}}'''
new='''      async function cloudStartMic(ev){{
        if(ev){{ev.preventDefault();ev.stopImmediatePropagation()}}
        if(!voiceStageOpen)openVoiceStage();
        if(voiceTranscribing){{
          if(voiceStageOpen)setVoiceStage('Sto trascrivendo','Un attimo…','Attendo la fine della registrazione precedente.');
          return;
        }}
        if(cloudRecording){{await cloudStopAndTranscribe();return}}'''
if old not in s: raise RuntimeError('R59 mic guard anchor missing')
s=s.replace(old,new,1)

# When a fresh recording starts, clear stale empty-STT only after explicit user gesture.
old='''          cloudSpeechSeen=false;cloudLastSpeechAt=0;
          cloudRecorder.start(250);'''
new='''          if(ev)consecutiveEmptyStt=0;
          cloudSpeechSeen=false;cloudLastSpeechAt=0;
          cloudRecorder.start(250);'''
if old not in s: raise RuntimeError('R59 recorder start anchor missing')
s=s.replace(old,new,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r59] PASS voice-state-reset stt-422-benign no-chat-spam transcribe-guard',flush=True)
