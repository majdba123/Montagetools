(function(){
  const fs=require('fs'), path=require('path'), cp=require('child_process'), os=require('os');
  const RELEASE_VERSION='31.0.25';
  const $=id=>document.getElementById(id), logEl=$('log'), btn=$('buildBtn');
  let packagePath='', voicePath='', lastBuildRoot='', lastOutputPath='';

  function log(s){ logEl.textContent += String(s)+'\n'; logEl.scrollTop=logEl.scrollHeight; }

  // CEP on Windows may return any of these forms depending on host/version:
  //   C:\Users\...\extension
  //   C:/Users/.../extension
  //   /C:/Users/.../extension
  //   file:///C:/Users/.../extension
  // V20.0.1 did not normalize the leading /C:/ form and could construct C:\C:\... .
  function normalizeLocalPath(raw){
    let s=String(raw||'').trim();
    if(!s) return '';
    try{s=decodeURI(s);}catch(_e){}
    s=s.replace(/^file:(?:\/\/\/|\/\/|\/)/i,'');
    if(process.platform==='win32'){
      s=s.replace(/\//g,'\\');
      if(/^\\[A-Za-z]:\\/.test(s)) s=s.substring(1);
      s=path.win32.normalize(s);
      if(/^[A-Za-z]:\\[A-Za-z]:\\/.test(s)) throw new Error('Repeated Windows drive prefix: '+s);
    }else{
      s=path.normalize(s);
    }
    return s;
  }

  function samePath(a,b){
    try{
      const x=normalizeLocalPath(a), y=normalizeLocalPath(b);
      return process.platform==='win32' ? x.toLowerCase()===y.toLowerCase() : x===y;
    }catch(_e){return false;}
  }

  function cepPath(){
    let raw='';
    try{raw=window.__adobe_cep__.getSystemPath('extension');}catch(e){throw new Error('CEP extension path unavailable: '+e.message);}
    const p=normalizeLocalPath(raw);
    const abs=process.platform==='win32' ? path.win32.isAbsolute(p) : path.isAbsolute(p);
    if(!abs) throw new Error('CEP extension path is not absolute. raw='+raw+' normalized='+p);
    if(!fs.existsSync(p)) throw new Error('CEP extension root does not exist. raw='+raw+' normalized='+p);
    return p;
  }

  let ext='';
  try{ext=cepPath();}
  catch(e){log('FATAL PATH CONTRACT: '+e.message);$('runtimeState').textContent='REPAIR REQUIRED';$('runtimeState').className='bad';}

  function runtimeRoot(){return path.join(process.env.LOCALAPPDATA||'', 'HEXA','VideoBuilderV31');}
  function runtimeConfigPath(){return path.join(runtimeRoot(),'runtime_config.json');}
  function runtimeLockPath(){return path.join(runtimeRoot(),'runtime_lock.json');}
  function defaultDiagRoot(){return runtimeRoot();}

  function loadRuntime(){
    try{
      if(!ext) throw new Error('Extension root failed path validation');
      const cfgPath=runtimeConfigPath();
      if(!fs.existsSync(cfgPath)) throw new Error('runtime_config.json missing; run Setup/Repair');
      const c=JSON.parse(fs.readFileSync(cfgPath,'utf8'));
      if(!c.python_exe||!fs.existsSync(c.python_exe)) throw new Error('Certified Python runtime missing: '+String(c.python_exe||''));
      if(c.downloads_during_build!==false) throw new Error('Unsafe runtime policy: downloads_during_build must be false');
      const lp=runtimeLockPath();
      if(!fs.existsSync(lp)) throw new Error('runtime_lock.json missing; run V'+RELEASE_VERSION+' Setup/Repair');
      const lock=JSON.parse(fs.readFileSync(lp,'utf8'));
      if(lock.version!==RELEASE_VERSION) throw new Error('Runtime lock version mismatch: expected '+RELEASE_VERSION+', received '+String(lock.version));
      if(lock.bundle_id!=='com.hexaterminal.videobuilder.v31_0_1') throw new Error('Runtime lock bundle mismatch: '+String(lock.bundle_id));
      if(!samePath(lock.python_exe,c.python_exe)) throw new Error('Runtime Python differs from installer-certified Python');
      if(!samePath(lock.extension_root,ext)) throw new Error('Loaded CEP extension differs from installer-certified extension root');
      c.python_exe=normalizeLocalPath(c.python_exe);
      c.vendor_dir=normalizeLocalPath(c.vendor_dir||'');
      c.python_import_roots=Array.isArray(c.python_import_roots)?c.python_import_roots.map(x=>normalizeLocalPath(x)).filter(x=>x&&fs.existsSync(x)):[];
      if(!c.python_import_contract_sha256||!lock.python_import_contract_sha256||c.python_import_contract_sha256!==lock.python_import_contract_sha256) throw new Error('Runtime Python import contract mismatch; run Setup/Repair');
      c.ffmpeg_path=normalizeLocalPath(c.ffmpeg_path||'');
      $('runtimeState').textContent='READY';$('runtimeState').className='ok';return c;
    }catch(e){
      $('runtimeState').textContent='REPAIR REQUIRED';$('runtimeState').className='bad';log('Runtime not ready: '+e.message);return null;
    }
  }

  let runtime=loadRuntime();
  function ready(){btn.disabled=!(runtime&&ext&&packagePath&&voicePath);}

  $('packageInput').addEventListener('change',e=>{
    packagePath=e.target.files[0]?normalizeLocalPath(e.target.files[0].path):'';
    $('packageName').textContent=packagePath?path.basename(packagePath):'Select HEXA scene package';ready();
  });
  $('voiceInput').addEventListener('change',e=>{
    voicePath=e.target.files[0]?normalizeLocalPath(e.target.files[0].path):'';
    $('voiceName').textContent=voicePath?path.basename(voicePath):'Select MP3 / WAV';ready();
  });

  $('openDiag').addEventListener('click',()=>{
    const d=(lastBuildRoot&&fs.existsSync(lastBuildRoot))?lastBuildRoot:defaultDiagRoot();
    if(fs.existsSync(d)) cp.spawn('explorer.exe',[d],{detached:true,shell:false});
    else log('Diagnostics directory does not exist yet: '+d);
  });

  $('openOutput').addEventListener('click',()=>{
    if(!lastOutputPath)return;
    const d=path.dirname(lastOutputPath);
    if(fs.existsSync(d))cp.spawn('explorer.exe',[d],{detached:true,shell:false});
  });

  function jsxString(s){return '"'+String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"')+'"';}


  function runtimePythonPath(pyRoot){
    const roots=[normalizeLocalPath(pyRoot)];
    const add=(p)=>{p=normalizeLocalPath(p||'');if(p&&fs.existsSync(p)&&!roots.some(x=>samePath(x,p)))roots.push(p);};
    if(runtime&&Array.isArray(runtime.python_import_roots))runtime.python_import_roots.forEach(add);
    else if(runtime&&runtime.vendor_dir)add(runtime.vendor_dir);
    return roots.join(path.delimiter);
  }

  function launcherFailure(reason,extra){
    try{
      const d=path.join(defaultDiagRoot(),'launcher_failures');fs.mkdirSync(d,{recursive:true});
      const stamp=new Date().toISOString().replace(/[:.]/g,'-');
      const p=path.join(d,'LAUNCHER_FAILURE_'+stamp+'.json');
      const payload=Object.assign({schema:'HEXA_V31_LAUNCHER_FAILURE',version:RELEASE_VERSION,timestamp:new Date().toISOString(),reason:String(reason),extension_root:ext,runtime_config:runtimeConfigPath(),python_exe:runtime?runtime.python_exe:null,package_path:packagePath,voice_path:voicePath},extra||{});
      fs.writeFileSync(p,JSON.stringify(payload,null,2),'utf8');lastBuildRoot=d;return p;
    }catch(_e){return '';}
  }

  function readJsonSafe(p){try{return JSON.parse(fs.readFileSync(p,'utf8'));}catch(_e){return null;}}

  function probeProductionMp4FromCertification(productionCert){
    const m=productionCert&&productionCert.media_contract?productionCert.media_contract:null;
    if(!m)return {ok:false,reason:'MEDIA_CONTRACT_MISSING'};
    return {ok:m.pass===true,backend:m.probe_backend||'UNKNOWN',duration:Number(m.duration_seconds||0),width:m.video?Number(m.video.width||0):0,height:m.video?Number(m.video.height||0):0,has_audio:Number(m.audio_stream_count||0)>0,gates:m.gates||{},probe:m.raw||null};
  }

  function certifyProductionRender(result){
    try{
      const args=['-m','hexa_v31.cli','certify-production','--mp4',normalizeLocalPath(result.production_mp4_planned||result.production_mp4||''),'--expected-duration',String(Number(result.production_expected_duration_seconds||0)),'--extension-root',ext,'--out-dir',normalizeLocalPath(result.build_root||''),'--runtime-config',runtimeConfigPath()];
      const pyRoot=path.join(ext,'py');
      const toolDirs=[];if(runtime.ffmpeg_path)toolDirs.push(path.dirname(runtime.ffmpeg_path));if(runtime.ffprobe_path&&(!runtime.ffmpeg_path||!samePath(path.dirname(runtime.ffprobe_path),path.dirname(runtime.ffmpeg_path))))toolDirs.push(path.dirname(runtime.ffprobe_path));const runtimePath=toolDirs.join(path.delimiter)+(toolDirs.length?path.delimiter:'')+(process.env.PATH||'');
      const env=Object.assign({},process.env,{HEXA_V31_RUNTIME_CONFIG:runtimeConfigPath(),HEXA_V31_NO_RUNTIME_DOWNLOADS:'1',PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',HF_HUB_OFFLINE:'1',TRANSFORMERS_OFFLINE:'1',PYTHONPATH:runtimePythonPath(pyRoot),PATH:runtimePath});
      const r=cp.spawnSync(runtime.python_exe,args,{env:env,encoding:'utf8',windowsHide:true,shell:false,timeout:600000,maxBuffer:16*1024*1024});
      const text=String(r.stdout||'')+'\n'+String(r.stderr||'');let out=null;
      text.split(/\r?\n/).forEach(line=>{if(line.startsWith('HEXA_V31_PRODUCTION_CERT_JSON=')){try{out=JSON.parse(line.substring(line.indexOf('=')+1));}catch(_e){}}});
      if(!out)return {status:'FAIL',reason:'PRODUCTION_CERTIFIER_NO_RESULT',exit_code:r.status,detail:text.slice(-3000)};
      return out;
    }catch(e){return {status:'FAIL',reason:'PRODUCTION_CERTIFIER_EXCEPTION',detail:String(e)};}
  }

  function certifyPhysicalBuild(result,premiereResult){
    const mp4=result.production_mp4_planned||result.production_mp4||'',prproj=result.premiere_project_path||'',rrPath=result.premiere_runtime_report||'';
    let mp4Bytes=0,projectBytes=0;
    try{if(mp4&&fs.existsSync(mp4))mp4Bytes=fs.statSync(mp4).size;}catch(_e){}
    try{if(prproj&&fs.existsSync(prproj))projectBytes=fs.statSync(prproj).size;}catch(_e){}
    const rr=rrPath&&fs.existsSync(rrPath)?readJsonSafe(rrPath):null;
    const productionCert=(mp4Bytes>100000&&projectBytes>=4096)?certifyProductionRender(result):{status:'FAIL',reason:'OUTPUT_FILES_NOT_READY'};
    const probe=mp4Bytes>100000?probeProductionMp4FromCertification(productionCert):{ok:false,reason:'MP4_MISSING_OR_TOO_SMALL'};
    const runtimeOk=!!rr&&rr.status==='PASS'&&rr.stage==='COMPLETE'&&rr.engine_final_mp4_verified===true&&rr.motion_engine==='PRE_RENDERED_ANIMATED_SCENE_MEDIA'&&rr.text_engine==='PRE_RENDERED_SELECTIVE_TYPOGRAPHY'&&rr.transform_effect_required===false&&rr.still_image_keyframe_dependency===false&&Number(rr.premiere_keyframes_written||0)===0&&Number(rr.animated_scene_media_verified)===Number(rr.animated_scene_media_total)&&Number(rr.pre_rendered_motion_events_certified)===Number(rr.pre_rendered_motion_events_total)&&Number(rr.selective_text_events_certified)===Number(rr.selective_text_events_total);
    const productionArtifactOk=!!productionCert&&productionCert.artifact_integrity_pass===true;
    const referenceScore10=Number(result.reference_score_10_value||0);
    const productionReferenceOk=!!productionCert&&productionCert.reference_proxy_pass===true&&result.production_promotion_allowed===true&&referenceScore10>=8.0;
    const physicalOk=mp4Bytes>100000&&projectBytes>=4096&&runtimeOk&&probe.ok&&productionArtifactOk;
    const certStatus=physicalOk?(productionReferenceOk?'PASS':'REVIEW_REQUIRED'):'FAIL';
    const cert={schema:'HEXA_V31_PHYSICAL_CERTIFICATION',version:RELEASE_VERSION,status:certStatus,timestamp:new Date().toISOString(),premiere_result:String(premiereResult),mp4_path:mp4,mp4_bytes:mp4Bytes,project_path:prproj,project_bytes:projectBytes,runtime_report_path:rrPath,runtime_report_status:rr?rr.status:null,runtime_report_stage:rr?rr.stage:null,animated_scene_media_total:rr?rr.animated_scene_media_total:null,animated_scene_media_verified:rr?rr.animated_scene_media_verified:null,pre_rendered_motion_events_total:rr?rr.pre_rendered_motion_events_total:null,pre_rendered_motion_events_certified:rr?rr.pre_rendered_motion_events_certified:null,selective_text_events_total:rr?rr.selective_text_events_total:null,selective_text_events_certified:rr?rr.selective_text_events_certified:null,premiere_keyframes_written:rr?rr.premiere_keyframes_written:null,engine_final_mp4_verified:rr?rr.engine_final_mp4_verified:null,engine_final_mp4_path:rr?rr.engine_final_mp4_path:null,engine_final_mp4_bytes:rr?rr.engine_final_mp4_bytes:null,motion_engine:rr?rr.motion_engine:null,text_engine:rr?rr.text_engine:null,still_image_keyframe_dependency:rr?rr.still_image_keyframe_dependency:null,transform_effect_required:rr?rr.transform_effect_required:null,media_probe:probe,ffprobe:probe,production_render_certification:productionCert,production_reference_proxy_pass:productionReferenceOk,production_reference_fidelity_proxy_score_percent:productionCert?productionCert.reference_fidelity_proxy_score_percent:null,reference_only_score_10:referenceScore10,reference_only_target_10:8.0,human_reference_comparison_pending:true};
    try{if(result.physical_certification){fs.writeFileSync(result.physical_certification,JSON.stringify(cert,null,2),'utf8');}}
    catch(_e){}
    try{if(result.build_root){const rp=path.join(result.build_root,'HEXA_V31_BUILD_RESULT.json');const j=fs.existsSync(rp)?readJsonSafe(rp):result;if(j){j.status=certStatus;j.premiere_export_pending=false;j.premiere_project_pending=!physicalOk;j.physical_certification_pass=physicalOk;j.quality_review_required=!productionReferenceOk;j.production_promotion_allowed=productionReferenceOk;j.reference_score_10_value=referenceScore10;j.production_mp4_bytes=mp4Bytes;j.premiere_project_bytes=projectBytes;j.production_render_reference_proxy_pass=productionReferenceOk;j.production_render_reference_score_percent=cert.production_reference_fidelity_proxy_score_percent;fs.writeFileSync(rp,JSON.stringify(j,null,2),'utf8');}}}catch(_e){}
    return cert;
  }

  btn.addEventListener('click',()=>{
    runtime=loadRuntime();if(!runtime){ready();return;}
    btn.disabled=true;logEl.textContent='';$('phase').textContent='BUILDING';$('phase').className='';$('barFill').style.width='5%';$('progressText').textContent='0 / 0';

    const py=runtime.python_exe;
    const pyRoot=path.join(ext,'py');
    if(!fs.existsSync(path.join(pyRoot,'hexa_v31','cli.py'))){
      const fp=launcherFailure('ENGINE_MODULE_MISSING',{expected_cli:path.join(pyRoot,'hexa_v31','cli.py')});
      log('BUILD BLOCKED: V31 engine module missing.');if(fp)log('Launcher diagnostic: '+fp);$('phase').textContent='FAILED';$('phase').className='bad';btn.disabled=false;return;
    }

    // Module launch avoids constructing a Windows script path entirely. This permanently removes
    // the V20.0.1 C:\\C:\\... launcher failure class.
    const args=['-m','hexa_v31.cli','build','--package',packagePath,'--voice',voicePath,'--extension-root',ext];if(runtime.build_cache_root)args.push('--work-root',normalizeLocalPath(runtime.build_cache_root));
    const toolDirs=[];if(runtime.ffmpeg_path)toolDirs.push(path.dirname(runtime.ffmpeg_path));if(runtime.ffprobe_path&&(!runtime.ffmpeg_path||!samePath(path.dirname(runtime.ffprobe_path),path.dirname(runtime.ffmpeg_path))))toolDirs.push(path.dirname(runtime.ffprobe_path));const runtimePath=toolDirs.join(path.delimiter)+(toolDirs.length?path.delimiter:'')+(process.env.PATH||'');
    const env=Object.assign({},process.env,{
      HEXA_V31_RUNTIME_CONFIG:runtimeConfigPath(),HEXA_V31_NO_RUNTIME_DOWNLOADS:'1',PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',
      HF_HUB_OFFLINE:'1',TRANSFORMERS_OFFLINE:'1',PYTHONPATH:runtimePythonPath(pyRoot),PATH:runtimePath
    });

    log('HEXA V'+RELEASE_VERSION+' build started. Downloads are forbidden during BUILD.');
    log('Certified Python: '+py);
    log('Extension root: '+ext);
    log('Engine launch: python -m hexa_v31.cli');

    let result=null,failure=null,finished=false;
    let child=null;
    try{child=cp.spawn(py,args,{env:env,windowsHide:true,shell:false,cwd:ext});}
    catch(e){
      const fp=launcherFailure('SPAWN_THROW',{error:String(e),args:args});log('BUILD LAUNCH FAILED: '+e);if(fp)log('Launcher diagnostic: '+fp);$('phase').textContent='FAILED';$('phase').className='bad';btn.disabled=false;return;
    }

    function consume(chunk){
      const text=chunk.toString('utf8');
      text.split(/\r?\n/).filter(Boolean).forEach(line=>{
        log(line);
        if(line.startsWith('HEXA_V31_RESULT_JSON=')){try{result=JSON.parse(line.substring(line.indexOf('=')+1));}catch(_e){}}
        if(line.startsWith('HEXA_V31_FAILURE_JSON=')){try{failure=JSON.parse(line.substring(line.indexOf('=')+1));lastBuildRoot=failure.build_root||lastBuildRoot;}catch(_e){}}
        const pm=line.match(/progress=(\d+\/\d+)/);if(pm)$('progressText').textContent=pm[1];
        else if(line.includes('SCENE_START')){const m=line.match(/SCENE_\d+/);if(m)$('progressText').textContent=m[0];}
      });
    }
    child.stdout.on('data',consume);child.stderr.on('data',consume);
    child.on('error',err=>{
      if(finished)return;finished=true;
      const fp=launcherFailure('SPAWN_ERROR_EVENT',{error:String(err),args:args});
      log('BUILD LAUNCH FAILED: '+err);if(fp)log('Launcher diagnostic: '+fp);$('phase').textContent='FAILED';$('phase').className='bad';$('barFill').style.width='100%';btn.disabled=false;
    });
    child.on('close',code=>{
      if(finished)return;finished=true;
      if(code!==0||!result){
        $('barFill').style.width='100%';
        if(failure&&failure.production_mp4&&fs.existsSync(failure.production_mp4)){
          lastBuildRoot=failure.build_root||lastBuildRoot;lastOutputPath=failure.production_mp4;
          $('outputPath').textContent='REVIEW READY â†’ '+lastOutputPath;$('openOutput').disabled=false;
          $('phase').textContent='MP4 READY - TECHNICAL REVIEW REQUIRED';$('phase').className='';
          log('Engine technical QA blocked promotion, but the physical MP4 was preserved: '+lastOutputPath);
        }else{$('phase').textContent='FAILED';$('phase').className='bad';}
        if(failure&&failure.diagnostic_id)log('Diagnostic ID: '+failure.diagnostic_id);
        if(failure&&failure.failure_bundle)log('Failure bundle: '+failure.failure_bundle);
        if(!failure){const fp=launcherFailure('ENGINE_EXIT_WITHOUT_RESULT',{exit_code:code,args:args});if(fp)log('Launcher diagnostic: '+fp);}
        log(failure&&failure.artifact_preserved?'BUILD TECHNICAL QA FAILED; MP4 PRESERVED FOR REVIEW.':'BUILD FAILED. Open Diagnostics and send the failure bundle/logs.');btn.disabled=false;return;
      }
      lastBuildRoot=result.build_root||'';lastOutputPath=result.production_mp4_planned||result.production_mp4||'';
      if(lastOutputPath){$('outputPath').textContent='READY â†’ '+lastOutputPath;$('openOutput').disabled=!fs.existsSync(lastOutputPath);log('Final MP4 already assembled and certified by V31 engine: '+lastOutputPath);}
      $('phase').textContent='MP4 READY â†’ PREMIERE PROJECT';$('barFill').style.width='90%';
      const jsx='$._hexaV31.assembleAndApply('+jsxString(result.edit_map)+')';
      log('Premiere execution mode: EDITABLE PROJECT ASSEMBLY + SAVE ONLY. Final MP4 export is already complete; Premiere export is forbidden in V31.');
      window.__adobe_cep__.evalScript(jsx,function(res){
        log('Premiere: '+res);
        if(String(res).indexOf('PASS')===0){
          const cert=certifyPhysicalBuild(result,res);
          if(cert.status==='PASS'){$('outputPath').textContent=lastOutputPath;$('openOutput').disabled=false;$('phase').textContent='BUILD PASS - V31.0.25';$('phase').className='ok';$('barFill').style.width='100%';log('HEXA Video Builder V31.0.25 physical Premiere assembly: PASS.');log('Animated Scene media in Premiere: PASS ('+String(cert.animated_scene_media_verified)+'/'+String(cert.animated_scene_media_total)+' clips).');log('Visible motion pre-render: PASS ('+String(cert.pre_rendered_motion_events_certified)+'/'+String(cert.pre_rendered_motion_events_total)+' events).');log('Selective Arabic typography: PASS ('+String(cert.selective_text_events_certified)+'/'+String(cert.selective_text_events_total)+' events).');log('Premiere project physical readback: PASS ('+cert.project_bytes+' bytes)');log('MP4 physical media validation: PASS ('+cert.mp4_bytes+' bytes, '+Number((cert.media_probe||cert.ffprobe).duration||0).toFixed(3)+'s, '+String((cert.media_probe||cert.ffprobe).backend||'probe')+').');log('Actual V31 final MP4 reference proxy: PASS ('+String(cert.production_reference_fidelity_proxy_score_percent)+'%).');log('Reference-only score: '+String(cert.reference_only_score_10)+'/10 (promotion floor 8.0).');log('MP4 saved to Documents: '+lastOutputPath);log('Human comparison with the reference videos remains the final visual quality gate.');}
          else if(cert.status==='REVIEW_REQUIRED'){$('outputPath').textContent=lastOutputPath;$('openOutput').disabled=false;$('phase').textContent='REVIEW REQUIRED - V31.0.25';$('phase').className='';$('barFill').style.width='100%';log('Physical MP4 + Premiere project: PASS.');log('Automated reference promotion gate: REVIEW REQUIRED ('+String(cert.production_reference_fidelity_proxy_score_percent)+'%, '+String(cert.reference_only_score_10)+'/10).');log('The MP4 is intentionally preserved and available for visual comparison.');log('Production promotion remains blocked until the reference gate passes or a human review confirms the next correction.');log('MP4 saved to Documents: '+lastOutputPath);}
          else{const fp=launcherFailure('PHYSICAL_CERTIFICATION_FAILED',{premiere_result:String(res),build_root:lastBuildRoot,edit_map:result.edit_map,expected_mp4:lastOutputPath,certification:cert});$('phase').textContent='CERTIFICATION FAILED - V31.0.25';$('phase').className='bad';$('barFill').style.width='100%';log('Premiere returned PASS, but physical artifact certification failed: '+String((cert.production_render_certification&&cert.production_render_certification.reason)||(cert.media_probe&&cert.media_probe.reason)||(cert.ffprobe&&cert.ffprobe.reason)||'runtime/project/output gate'));if(fp)log('Launcher diagnostic: '+fp);}
        }
        else{const fp=launcherFailure('PREMIERE_NATIVE_EXECUTION_FAILED',{premiere_result:String(res),build_root:lastBuildRoot,edit_map:result.edit_map,expected_mp4:lastOutputPath});$('phase').textContent='MP4 READY - PREMIERE PROJECT FAILED';$('phase').className='bad';$('barFill').style.width='100%';log('Premiere project assembly/save failed. The engine MP4 remains available; diagnostics preserved.');if(fp)log('Launcher diagnostic: '+fp);}
        btn.disabled=false;
      });
    });
  });
  ready();
})();


