from __future__ import annotations
import os, pathlib, shutil, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'/'py'))
from hexa_v31.media_probe import summarize_media
from hexa_v31.audio import probe_audio

ff=shutil.which('ffmpeg')
if not ff:
    print('V31_0_1_MEDIA_PROBE_FALLBACK_SKIP_NO_FFMPEG'); raise SystemExit(0)
with tempfile.TemporaryDirectory() as td:
    td=pathlib.Path(td); mp4=td/'probe.mp4'
    cmd=[ff,'-nostdin','-y','-v','error','-f','lavfi','-i','color=c=white:s=1920x1080:r=30:d=1.2','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-shortest','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(mp4)]
    cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
    if cp.returncode!=0:raise AssertionError(cp.stderr[-2000:])
    m=summarize_media(mp4,ffprobe='',ffmpeg=ff,timeout=30)
    assert m['backend']=='FFMPEG_STDERR_FALLBACK',m
    assert m['video'] and int(m['video']['width'])==1920 and int(m['video']['height'])==1080,m
    assert m['audio_streams'],m
    assert 0.9 <= float(m['duration_seconds']) <= 1.5,m

    # Audio-only preflight must also survive a machine with ffmpeg but no ffprobe.
    import wave, os
    wav=td/'voice.wav'
    with wave.open(str(wav),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*16000)
    old_path=os.environ.get('PATH','');old_ff=os.environ.get('HEXA_FFMPEG');old_fp=os.environ.get('HEXA_FFPROBE')
    try:
        os.environ['PATH']=str(td)
        os.environ['HEXA_FFMPEG']=ff
        os.environ.pop('HEXA_FFPROBE',None)
        a=probe_audio(wav)
        assert a['probe_backend']=='FFMPEG_STDERR_FALLBACK',a
        assert 0.8 <= float(a['duration_seconds']) <= 1.2,a
    finally:
        os.environ['PATH']=old_path
        if old_ff is None:os.environ.pop('HEXA_FFMPEG',None)
        else:os.environ['HEXA_FFMPEG']=old_ff
        if old_fp is None:os.environ.pop('HEXA_FFPROBE',None)
        else:os.environ['HEXA_FFPROBE']=old_fp

ins=(ROOT/'tools'/'install_v31.py').read_text(encoding='utf-8')
assert "FFPROBE OPTIONAL: not available" in ins
assert "raise RuntimeError('ffprobe not found beside ffmpeg or PATH.')" not in ins
assert '\'numpy\':\'assert hasattr(m,"array") and hasattr(m,"ndarray")\'' in ins
assert "from faster_whisper import WhisperModel" in ins
print('V31_0_1_MEDIA_PROBE_FALLBACK_PASS')
