from __future__ import annotations
import math, os, pathlib, subprocess, wave
import numpy as np
from hexa_v31.util import ensure_dir, ffmpeg_exe, run_checked, sha256_file, write_json
from hexa_v31.media_probe import summarize_media

class AudioError(RuntimeError): pass


def probe_audio(path: str|os.PathLike) -> dict:
    p=pathlib.Path(path)
    if not p.is_file(): raise AudioError(f'Voice over not found: {p}')
    try:
        media=summarize_media(p,timeout=30)
    except Exception as e:
        raise AudioError('Voice-over media probe failed: '+str(e)) from e
    dur=float(media.get('duration_seconds') or 0)
    if dur<=0: raise AudioError('Invalid or zero-duration voice over')
    if not media.get('audio_streams'):
        raise AudioError('Voice-over file has no audio stream')
    return {'path':str(p.resolve()),'sha256':sha256_file(p),'duration_seconds':dur,'probe':media.get('raw'),'probe_backend':media.get('backend')}


def decode_mono16k(path: str|os.PathLike, out_wav: str|os.PathLike) -> pathlib.Path:
    ff=ffmpeg_exe()
    if not ff: raise AudioError('ffmpeg not found. Run V20 Setup/Repair.')
    out=pathlib.Path(out_wav); out.parent.mkdir(parents=True,exist_ok=True)
    run_checked([ff,'-nostdin','-y','-v','error','-i',str(path),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(out)],timeout=180)
    return out


def load_wav_mono(path: str|os.PathLike):
    with wave.open(str(path),'rb') as w:
        sr=w.getframerate(); ch=w.getnchannels(); sw=w.getsampwidth(); n=w.getnframes(); raw=w.readframes(n)
    if ch!=1 or sw!=2: raise AudioError('Expected mono 16-bit PCM WAV')
    x=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768.0
    return x,sr


def rms_envelope(x: np.ndarray, sr: int, hop_ms: float=10.0, win_ms: float=30.0):
    hop=max(1,int(sr*hop_ms/1000)); win=max(hop,int(sr*win_ms/1000))
    if len(x)<win: return np.array([float(np.sqrt(np.mean(x*x)+1e-12))]), np.array([0.0])
    sq=x.astype(np.float64)**2
    cs=np.concatenate(([0.0],np.cumsum(sq)))
    starts=np.arange(0,len(x)-win+1,hop,dtype=np.int64)
    means=(cs[starts+win]-cs[starts])/win
    rms=np.sqrt(means+1e-12)
    times=(starts+win*0.5)/sr
    return rms.astype(np.float32),times.astype(np.float32)
