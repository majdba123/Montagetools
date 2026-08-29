from __future__ import annotations
import json, os, pathlib, re, subprocess
from typing import Any
from .util import ffmpeg_exe, ffprobe_exe

_DURATION_RE = re.compile(r'Duration:\s*(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)', re.I)
_VIDEO_RE = re.compile(r'Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5})(?:[\s,]|$)', re.I)
_AUDIO_RE = re.compile(r'Audio:\s*([^,\s]+)', re.I)
_FPS_RE = re.compile(r'(\d+(?:\.\d+)?)\s*fps\b', re.I)


def _duration_seconds(text: str) -> float:
    m=_DURATION_RE.search(text or '')
    if not m:return 0.0
    return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))


def _ffprobe_json(path:pathlib.Path, ffprobe:str, timeout:int=60)->dict[str,Any]:
    cmd=[ffprobe,'-v','error','-show_entries','format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels','-of','json',str(path)]
    cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if cp.returncode!=0:
        raise RuntimeError('ffprobe failed: '+(cp.stderr or cp.stdout or '')[-1500:])
    d=json.loads(cp.stdout or '{}')
    d['_hexa_probe_backend']='FFPROBE_JSON'
    return d


def _ffmpeg_header_probe(path:pathlib.Path, ffmpeg:str, timeout:int=60)->dict[str,Any]:
    # Decode only a tiny prefix. FFmpeg prints container/stream metadata before decoding,
    # which makes this a safe fallback when a legacy HEXA FFmpeg bundle lacks ffprobe.exe.
    sink='NUL' if os.name=='nt' else '/dev/null'
    cmd=[ffmpeg,'-hide_banner','-nostdin','-i',str(path),'-t','0.05','-map','0:v:0?','-map','0:a:0?','-f','null',sink]
    cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    text=(cp.stderr or '')+'\n'+(cp.stdout or '')
    # FFmpeg may return non-zero for a malformed file. A valid media file should expose
    # Duration and at least one stream header even if the tiny decode has warnings.
    dur=_duration_seconds(text)
    streams=[]
    for line in text.splitlines():
        if 'Stream #' not in line:continue
        vm=_VIDEO_RE.search(line)
        if vm:
            fpsm=_FPS_RE.search(line)
            fps=float(fpsm.group(1)) if fpsm else 0.0
            streams.append({'codec_type':'video','codec_name':vm.group(1),'width':int(vm.group(2)),'height':int(vm.group(3)),'r_frame_rate':str(fps) if fps else ''})
            continue
        am=_AUDIO_RE.search(line)
        if am:
            streams.append({'codec_type':'audio','codec_name':am.group(1)})
    if dur<=0 or not streams:
        raise RuntimeError('ffmpeg metadata fallback could not establish media contract: '+text[-2200:])
    return {
        'format':{'duration':str(dur),'size':str(path.stat().st_size)},
        'streams':streams,
        '_hexa_probe_backend':'FFMPEG_STDERR_FALLBACK',
        '_hexa_ffmpeg_returncode':cp.returncode,
    }


def probe_media_json(path: str|os.PathLike, *, ffprobe: str|None=None, ffmpeg: str|None=None, timeout:int=60)->dict[str,Any]:
    p=pathlib.Path(path)
    if not p.is_file():raise RuntimeError('Media file not found: '+str(p))
    fp=ffprobe if ffprobe is not None else ffprobe_exe()
    if fp:
        try:
            q=pathlib.Path(fp)
            if q.is_file():return _ffprobe_json(p,str(q),timeout)
        except Exception:
            # Fallback is intentional. A stale/broken ffprobe must not block a working FFmpeg runtime.
            pass
    ff=ffmpeg if ffmpeg is not None else ffmpeg_exe()
    if not ff or not pathlib.Path(ff).is_file():
        raise RuntimeError('Neither usable ffprobe nor ffmpeg is available for media probing')
    return _ffmpeg_header_probe(p,str(ff),timeout)


def summarize_media(path: str|os.PathLike, *, ffprobe: str|None=None, ffmpeg: str|None=None, timeout:int=60)->dict[str,Any]:
    raw=probe_media_json(path,ffprobe=ffprobe,ffmpeg=ffmpeg,timeout=timeout)
    streams=raw.get('streams') or []
    videos=[x for x in streams if x.get('codec_type')=='video']
    audios=[x for x in streams if x.get('codec_type')=='audio']
    dur=float((raw.get('format') or {}).get('duration') or 0.0)
    return {
        'backend':raw.get('_hexa_probe_backend'),
        'duration_seconds':dur,
        'size_bytes':int((raw.get('format') or {}).get('size') or pathlib.Path(path).stat().st_size),
        'video':videos[0] if videos else None,
        'audio_streams':audios,
        'raw':raw,
    }
