from __future__ import annotations
import hashlib, json, os, pathlib, re, shutil, subprocess, tempfile, unicodedata
from typing import Any, Iterable


def sha256_file(path: os.PathLike | str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: os.PathLike | str) -> Any:
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def write_json(path: os.PathLike | str, data: Any) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write('\n')
    os.replace(tmp, p)


def write_text(path: os.PathLike | str, text: str) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, p)


def ensure_dir(path: os.PathLike | str) -> pathlib.Path:
    p = pathlib.Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def normalize_arabic(s: str) -> str:
    # Match-only normalization. Canonical source text is never mutated.
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'[\u064B-\u065F\u0670\u06D6-\u06ED]', '', s)
    s = s.replace('ـ', '')
    s = re.sub('[إأآٱ]', 'ا', s)
    s = s.replace('ى', 'ي').replace('ؤ', 'و').replace('ئ', 'ي')
    s = re.sub(r'[^\w\u0600-\u06FF]+', ' ', s, flags=re.UNICODE)
    s = re.sub(r'[_\d]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip().lower()


def canonical_words_with_offsets(text: str):
    out = []
    for m in re.finditer(r'\S+', text, flags=re.UNICODE):
        raw = m.group(0)
        n = normalize_arabic(raw)
        if n:
            out.append({'raw': raw, 'norm': n, 'start': m.start(), 'end': m.end()})
    return out


def _tool_from_env_or_path(env_name: str, *names: str) -> str | None:
    raw = os.environ.get(env_name)
    if raw:
        try:
            p = pathlib.Path(raw)
            if p.is_file():
                return str(p)
        except Exception:
            pass
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    return None


def ffmpeg_exe() -> str | None:
    return _tool_from_env_or_path('HEXA_FFMPEG', 'ffmpeg', 'ffmpeg.exe')


def ffprobe_exe() -> str | None:
    return _tool_from_env_or_path('HEXA_FFPROBE', 'ffprobe', 'ffprobe.exe')


def run_checked(cmd: list[str], timeout: int = 120, cwd: str | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f'Command failed ({p.returncode}): {cmd}\nSTDOUT:\n{p.stdout[-3000:]}\nSTDERR:\n{p.stderr[-3000:]}')
    return p


def path_is_within(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def safe_filename(s: str, maxlen: int = 90) -> str:
    s = re.sub(r'[^A-Za-z0-9_.-]+', '_', s).strip('._')
    return (s or 'item')[:maxlen]


def atomic_copy(src: os.PathLike | str, dst: os.PathLike | str) -> None:
    dst = pathlib.Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(dst.parent), delete=False) as tf:
        tmp = pathlib.Path(tf.name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)



def documents_dir() -> pathlib.Path:
    """Return the user's real Windows Documents known folder when available.

    Uses SHGetKnownFolderPath on Windows so OneDrive/redirected Documents is respected.
    Falls back conservatively on other platforms / older Windows environments.
    """
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            class GUID(ctypes.Structure):
                _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte*8)(0xAD,0xB4,0x6C,0x85,0x48,0x03,0x69,0xC7))
            out = ctypes.c_wchar_p()
            hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out))
            if hr == 0 and out.value:
                val = pathlib.Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return val
        except Exception:
            pass
    up = os.environ.get('USERPROFILE')
    if up:
        return pathlib.Path(up) / 'Documents'
    return pathlib.Path.home() / 'Documents'
