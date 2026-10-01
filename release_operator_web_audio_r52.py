from pathlib import Path
import py_compile
P=Path('/data/top2_app/asd_app/routes_operator_bodymind.py')
s=P.read_text(encoding='utf-8',errors='replace')
old="            await cloudAudio.play();"
new="            await playCloudVoiceBytes(await blob.arrayBuffer(),usageId);  // BODYMIND_R52_WEB_AUDIO_TTS"
if old in s:
    s=s.replace(old,new,1)
elif "BODYMIND_R52_WEB_AUDIO_TTS" not in s:
    raise RuntimeError("R52 TTS play anchor missing")
P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-web-audio-r52] PASS',flush=True)
