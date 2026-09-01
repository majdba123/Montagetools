from __future__ import annotations
"""Offline PCM prosody projected onto immutable word-alignment intervals."""
import wave
import numpy as np

class AudioProsodyAnalyzer:
    version='HEXA_AUDIO_PROSODY_ANALYZER_V1'
    def analyze(self,wav_path,alignment):
        with wave.open(str(wav_path),'rb') as wf:
            rate=wf.getframerate();channels=wf.getnchannels();width=wf.getsampwidth();raw=wf.readframes(wf.getnframes())
        if width!=2:raise ValueError('AudioProsodyAnalyzer requires cached PCM16 mono-compatible WAV')
        samples=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768.0
        if channels>1:samples=samples.reshape(-1,channels).mean(axis=1)
        frame=max(1,int(rate*.040));hop=max(1,int(rate*.020));rms=np.array([np.sqrt(np.mean(samples[i:i+frame]**2)) for i in range(0,max(1,len(samples)-frame+1),hop)],dtype=np.float32)
        words=sorted(alignment.get('word_timings') or [],key=lambda w:float(w.get('start',0)));rows=[]
        for i,w in enumerate(words):
            st=max(0.,float(w.get('start',0)));en=max(st+.001,float(w.get('end',st)));a=int(st*rate/hop);b=max(a+1,int(en*rate/hop));local=rms[a:min(len(rms),b)] if len(rms) else np.array([0.])
            before=max(0.,st-float(words[i-1].get('end',st))) if i else st;after=max(0.,float(words[i+1].get('start',en))-en) if i+1<len(words) else 0.
            if not len(local):local=np.array([0.],dtype=np.float32)
            baseline=rms[max(0,a-3):min(len(rms),a+1)] if len(rms) else np.array([0.],dtype=np.float32)
            if not len(baseline):baseline=np.array([0.],dtype=np.float32)
            energy=float(local.mean());onset=float(max(0.,local.max()-np.median(baseline)))
            rows.append({'start':round(st,6),'end':round(en,6),'rms':round(energy,7),'energy':round(energy,7),'onset_strength':round(onset,7),'pause_before':round(before,6),'pause_after':round(after,6)})
        return {'version':self.version,'sample_rate':rate,'frame_seconds':.040,'hop_seconds':.020,'word_features':rows,'nonzero_energy_count':sum(1 for r in rows if r['energy']>0),'source':'CACHED_16K_MONO_PCM'}
