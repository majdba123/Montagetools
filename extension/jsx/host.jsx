$._hexaV31 = {
  TICKS_PER_SECOND:254016000000,

  _readJSON:function(p){var f=new File(p);if(!f.exists)throw new Error('JSON not found: '+p);f.encoding='UTF-8';f.open('r');var s=f.read();f.close();return JSON.parse(s);},
  _writeJSON:function(p,o){try{var f=new File(p);f.encoding='UTF-8';if(!f.parent.exists)f.parent.create();if(!f.open('w'))return false;f.write(JSON.stringify(o,null,2));f.close();return true;}catch(_e){return false;}},
  _canon:function(p){try{return String(new File(p).fsName).replace(/\//g,'\\').toLowerCase();}catch(_e){return String(p||'').replace(/\//g,'\\').toLowerCase();}},
  _ticks:function(sec){return String(Math.max(0,Math.round((Number(sec)||0)*this.TICKS_PER_SECOND)));},
  _time:function(sec){var t=new Time();t.seconds=Math.max(0,Number(sec)||0);return t;},
  _fps:function(seq){try{var tb=Number(seq.timebase);if(tb>0)return this.TICKS_PER_SECOND/tb;}catch(_e){}return 0;},

  _findSequence:function(name){for(var i=0;i<app.project.sequences.numSequences;i++){var s=app.project.sequences[i];if(s&&s.name===name)return s;}return null;},
  _deleteSequencesNamed:function(name){var rows=[];for(var i=0;i<app.project.sequences.numSequences;i++){var s=app.project.sequences[i];if(s&&s.name===name)rows.push(s);}var n=0;for(var j=0;j<rows.length;j++){try{if(app.project.deleteSequence(rows[j]))n++;}catch(_e){}}return n;},
  _openSequence:function(seq){try{if(app.project.openSequence)app.project.openSequence(seq.sequenceID);}catch(_e){} return app.project.activeSequence||seq;},

  _findProjectItem:function(root,path){
    var want=this._canon(path),stack=[root];
    while(stack.length){
      var item=stack.pop();
      try{var mp=item.getMediaPath?item.getMediaPath():'';if(mp&&this._canon(mp)===want)return item;}catch(_e){}
      try{if(item.children&&item.children.numItems){for(var i=0;i<item.children.numItems;i++)stack.push(item.children[i]);}}catch(_e2){}
    }
    return null;
  },
  _makeBin:function(name){try{var b=app.project.rootItem.createBin(name);if(b)return b;}catch(_e){}return app.project.rootItem;},
  _importOne:function(path,targetBin){var ex=this._findProjectItem(app.project.rootItem,path);if(ex)return ex;var ok=app.project.importFiles([path],true,targetBin||app.project.rootItem,false);if(!ok)throw new Error('Premiere importFiles returned false for '+path);var it=this._findProjectItem(app.project.rootItem,path);if(!it)throw new Error('Imported media could not be resolved by path: '+path);return it;},
  _ensureImported:function(paths,targetBin){
    var missing=[],seen={},map={};
    for(var i=0;i<paths.length;i++){
      var p=String(paths[i]||'');if(!p)continue;var k=this._canon(p);if(seen[k])continue;seen[k]=true;
      var ex=this._findProjectItem(app.project.rootItem,p);if(ex)map[k]=ex;else missing.push(p);
    }
    if(missing.length){var ok=app.project.importFiles(missing,true,targetBin||app.project.rootItem,false);if(!ok)throw new Error('Bulk media import returned false for '+missing.length+' files');}
    for(var j=0;j<paths.length;j++){var pp=String(paths[j]||'');if(!pp)continue;var kk=this._canon(pp);if(!map[kk])map[kk]=this._findProjectItem(app.project.rootItem,pp);if(!map[kk])throw new Error('Media missing after import: '+pp);}
    return map;
  },

  _removeBootstrap:function(seq,bootstrapPath){var want=this._canon(bootstrapPath),removed=0;
    function sweep(tracks,canon){for(var t=0;t<tracks.numTracks;t++){var tr=tracks[t];for(var c=tr.clips.numItems-1;c>=0;c--){var cl=tr.clips[c],mp='';try{mp=cl.projectItem&&cl.projectItem.getMediaPath?cl.projectItem.getMediaPath():'';}catch(_e){}if(mp&&canon(mp)===want){try{cl.remove(false,false);removed++;}catch(_e2){}}}}}
    sweep(seq.videoTracks,this._canon);sweep(seq.audioTracks,this._canon);return removed;
  },

  _ensureTracks:function(seq,vCount,aCount){
    seq=this._openSequence(seq);app.enableQE();var qseq=qe.project.getActiveSequence();if(!qseq)throw new Error('QE active sequence unavailable while adding tracks');
    var guard=0;
    while(seq.videoTracks.numTracks<vCount&&guard<24){guard++;var before=seq.videoTracks.numTracks;try{qseq.addTracks(1,Math.max(0,before-1),0);}catch(_e){try{qseq.addTracks(1);}catch(_e2){}}if(seq.videoTracks.numTracks<=before)throw new Error('Unable to add required Premiere video track '+before);}
    guard=0;
    while(seq.audioTracks.numTracks<aCount&&guard<8){guard++;var ab=seq.audioTracks.numTracks;try{qseq.addTracks(0);}catch(_e3){}if(seq.audioTracks.numTracks<=ab)throw new Error('Unable to add required Premiere audio track '+ab);}
    return {video:seq.videoTracks.numTracks,audio:seq.audioTracks.numTracks};
  },

  _findTrackClipAt:function(track,path,startSec){var want=this._canon(path),best=null,bestDelta=999999;
    for(var c=0;c<track.clips.numItems;c++){var cl=track.clips[c],mp='';try{mp=cl.projectItem&&cl.projectItem.getMediaPath?cl.projectItem.getMediaPath():'';}catch(_e){}if(!mp||this._canon(mp)!==want)continue;var st=0;try{st=Number(cl.start.seconds)||0;}catch(_e2){}var d=Math.abs(st-Number(startSec||0));if(d<bestDelta){best=cl;bestDelta=d;}}
    return bestDelta<=0.12?best:null;
  },
  _placeVideoItem:function(seq,row,itemMap){var ti=Number(row.premiere_track_index);if(ti<0||ti>=seq.videoTracks.numTracks)throw new Error('Video track index out of range: '+ti+' for '+row.clip_display_name);var tr=seq.videoTracks[ti],pi=itemMap[this._canon(row.source_path)];if(!pi)throw new Error('ProjectItem missing for '+row.source_path);var ok=tr.overwriteClip(pi,this._ticks(row.start_seconds));if(ok===false)throw new Error('overwriteClip failed for '+row.clip_display_name);var cl=this._findTrackClipAt(tr,row.source_path,row.start_seconds);if(!cl)throw new Error('Placed video clip could not be resolved: '+row.clip_display_name);try{cl.name=row.clip_display_name;}catch(_e){}try{cl.start=this._time(row.start_seconds);}catch(_e2){}try{cl.end=this._time(row.end_seconds);}catch(e){throw new Error('Unable to trim video clip '+row.clip_display_name+': '+e.toString());}return cl;},
  _placeAudioItem:function(seq,row,itemMap){var ti=Number(row.premiere_track_index||0);if(ti<0||ti>=seq.audioTracks.numTracks)throw new Error('Audio track index out of range: '+ti);var tr=seq.audioTracks[ti],pi=itemMap[this._canon(row.source_path)];if(!pi)throw new Error('Audio ProjectItem missing for '+row.source_path);var ok=tr.overwriteClip(pi,this._ticks(row.start_seconds));if(ok===false)throw new Error('Audio overwriteClip failed');var cl=this._findTrackClipAt(tr,row.source_path,row.start_seconds);if(!cl)throw new Error('Placed audio clip could not be resolved');try{cl.name=row.clip_display_name;}catch(_e){}try{cl.start=this._time(row.start_seconds);}catch(_e2){}try{cl.end=this._time(row.end_seconds);}catch(e){throw new Error('Unable to trim final voice over: '+e.toString());}return cl;},
  _certifyPlacedClip:function(cl,row,kind,fps){
    if(!cl)throw new Error(kind+' timeline readback missing for '+String(row.clip_display_name||''));
    var actualPath='';try{actualPath=cl.projectItem&&cl.projectItem.getMediaPath?cl.projectItem.getMediaPath():'';}catch(_e){}
    if(!actualPath||this._canon(actualPath)!==this._canon(row.source_path))throw new Error(kind+' media readback mismatch for '+String(row.clip_display_name||'')+': '+actualPath+' != '+String(row.source_path||''));
    var actualStart=NaN,actualEnd=NaN;try{actualStart=Number(cl.start.seconds);}catch(_e2){}try{actualEnd=Number(cl.end.seconds);}catch(_e3){}
    var expectedStart=Number(row.start_seconds),expectedEnd=Number(row.end_seconds),tol=Math.max(0.02,1/Math.max(1,Number(fps)||30)+0.01);
    if(!isFinite(actualStart)||Math.abs(actualStart-expectedStart)>tol)throw new Error(kind+' start readback mismatch for '+String(row.clip_display_name||'')+': '+actualStart+' != '+expectedStart);
    if(!isFinite(actualEnd)||Math.abs(actualEnd-expectedEnd)>tol)throw new Error(kind+' end readback mismatch for '+String(row.clip_display_name||'')+': '+actualEnd+' != '+expectedEnd);
    if(actualEnd<=actualStart)throw new Error(kind+' non-positive timeline duration for '+String(row.clip_display_name||''));
    return {clip_display_name:String(row.clip_display_name||''),source_path:String(actualPath),expected_start_seconds:expectedStart,actual_start_seconds:actualStart,expected_end_seconds:expectedEnd,actual_end_seconds:actualEnd,tolerance_seconds:tol};
  },

  _addMarkers:function(seq,rows){var n=0;if(!rows)return n;for(var i=0;i<rows.length;i++){try{var m=seq.markers.createMarker(Number(rows[i].seconds)||0);if(m){m.name=String(rows[i].name||'SCENE');n++;}}catch(_e){}}return n;},

  // V31.0.1 final assembly intentionally contains no ComponentParam keyframe helpers.
  // All visual motion and selective typography are pre-rendered into Scene video media.

  // V31.0.1 intentionally has no Premiere export helper.
  // The engine creates and certifies the final MP4 before Premiere project assembly.

  assembleAndApply:function(mapPath){
    var stage='INIT',report={schema:'HEXA_V31_PREMIERE_RUNTIME_REPORT',version:'31.0.25',status:'RUNNING',stage:'INIT',map_path:mapPath,started_at:(new Date()).toUTCString()};
    var reportPath='';
    try{
      if(!app.project)throw new Error('no Premiere project');
      stage='READ_EDIT_MAP';var data=this._readJSON(mapPath),a=data.assembly||{};reportPath=String(a.runtime_report_path||'');
      if(a.execution_mode!=='PREMIERE_2022_ANIMATED_SCENE_MEDIA_ASSEMBLY')throw new Error('Unsupported Premiere execution mode: '+String(a.execution_mode));
      if(a.xml_import_forbidden!==true)throw new Error('V31.0.25 safety contract requires xml_import_forbidden=true');
      if(a.export_required===true)throw new Error('V31.0.25 forbids Premiere MP4 export; engine_final_mp4 is the only export authority');
      report.execution_mode=a.execution_mode;
      report.motion_engine='PRE_RENDERED_ANIMATED_SCENE_MEDIA';
      report.text_engine='PRE_RENDERED_SELECTIVE_TYPOGRAPHY';
      report.transform_effect_required=false;
      report.still_image_keyframe_dependency=false;
      report.premiere_keyframes_written=0;
      report.pre_rendered_motion_events_total=Number(data.pre_rendered_motion_event_count||0);
      report.selective_text_events_total=Number(data.selective_text_event_count||0);
      report.final_mp4_authority=String(a.final_mp4_authority||'ENGINE_CONCAT_OF_IDENTICAL_ANIMATED_SCENE_MEDIA');
      report.stage=stage;if(reportPath)this._writeJSON(reportPath,report);

      stage='VERIFY_ENGINE_FINAL_MP4';var engineMp4=String(a.production_mp4_path||'');if(!engineMp4)throw new Error('Engine final MP4 path missing from edit map');var emf=new File(engineMp4);if(!emf.exists||Number(emf.length)<100000)throw new Error('Engine final MP4 missing/too small before Premiere assembly: '+engineMp4);report.stage=stage;report.engine_final_mp4_path=emf.fsName;report.engine_final_mp4_bytes=Number(emf.length);report.engine_final_mp4_verified=true;if(reportPath)this._writeJSON(reportPath,report);

      stage='RESET_MASTER_SEQUENCE';report.stage=stage;report.deleted_old_master_sequences=this._deleteSequencesNamed(String(a.sequence_name||'HEXA_V31_MASTER'));if(reportPath)this._writeJSON(reportPath,report);
      stage='IMPORT_BOOTSTRAP';var mediaBin=this._makeBin('HEXA_V31_MEDIA_'+(new Date().getTime()));var bootstrap=this._importOne(String(a.sequence_bootstrap_media),mediaBin);report.stage=stage;if(reportPath)this._writeJSON(reportPath,report);
      stage='CREATE_SEQUENCE';var seq=app.project.createNewSequenceFromClips(String(a.sequence_name||'HEXA_V31_MASTER'),[bootstrap],mediaBin);if(!seq||!seq.sequenceID)seq=this._findSequence(String(a.sequence_name||'HEXA_V31_MASTER'));if(!seq)throw new Error('createNewSequenceFromClips did not create the master sequence');seq=this._openSequence(seq);report.stage=stage;report.sequence_id=String(seq.sequenceID);report.bootstrap_removed=this._removeBootstrap(seq,String(a.sequence_bootstrap_media));if(reportPath)this._writeJSON(reportPath,report);
      stage='VERIFY_SEQUENCE_SETTINGS';var actualFps=this._fps(seq);report.stage=stage;report.sequence_settings={width:Number(seq.frameSizeHorizontal),height:Number(seq.frameSizeVertical),fps:actualFps,timebase:String(seq.timebase)};
      if(Number(seq.frameSizeHorizontal)!==Number(data.project.width)||Number(seq.frameSizeVertical)!==Number(data.project.height))throw new Error('Sequence size mismatch: '+seq.frameSizeHorizontal+'x'+seq.frameSizeVertical+' expected '+data.project.width+'x'+data.project.height);
      if(Math.abs(actualFps-Number(data.project.fps))>0.02)throw new Error('Sequence FPS mismatch: '+actualFps+' expected '+data.project.fps);if(reportPath)this._writeJSON(reportPath,report);
      stage='ENSURE_TRACKS';var tc=this._ensureTracks(seq,Number(a.required_video_tracks||1),Number(a.required_audio_tracks||1));report.stage=stage;report.tracks=tc;if(reportPath)this._writeJSON(reportPath,report);

      stage='VERIFY_ANIMATED_SCENE_MEDIA';var vrows=(a.video_items||[]).slice(0),i;
      if(!vrows.length)throw new Error('No animated Scene media supplied.');
      for(i=0;i<vrows.length;i++){
        if(String(vrows[i].item_role||'')!=='ANIMATED_SCENE_MEDIA')throw new Error('Non-animated media row in V31.0.25 final handoff: '+String(vrows[i].clip_display_name));
        var vf=new File(String(vrows[i].source_path||''));if(!vf.exists||Number(vf.length)<4096)throw new Error('Animated Scene media missing/too small: '+String(vrows[i].source_path));
      }
      report.stage=stage;report.animated_scene_media_total=vrows.length;report.animated_scene_media_verified=vrows.length;if(reportPath)this._writeJSON(reportPath,report);

      stage='IMPORT_MEDIA';var paths=[];for(i=0;i<vrows.length;i++)paths.push(vrows[i].source_path);for(i=0;i<(a.audio_items||[]).length;i++)paths.push(a.audio_items[i].source_path);var itemMap=this._ensureImported(paths,mediaBin);report.stage=stage;report.unique_media_count=0;for(var kk in itemMap)if(itemMap.hasOwnProperty(kk))report.unique_media_count++;if(reportPath)this._writeJSON(reportPath,report);
      stage='PLACE_VIDEO';vrows.sort(function(x,y){return Number(x.start_frame)-Number(y.start_frame);});var vp=0,videoReadback=[];for(i=0;i<vrows.length;i++){var vclip=this._placeVideoItem(seq,vrows[i],itemMap);videoReadback.push(this._certifyPlacedClip(vclip,vrows[i],'VIDEO',Number(data.project.fps)));vp++;}report.stage=stage;report.video_items_placed=vp;report.video_timeline_readback=videoReadback;if(reportPath)this._writeJSON(reportPath,report);
      stage='PLACE_AUDIO';var ap=0,audioReadback=[];for(i=0;i<(a.audio_items||[]).length;i++){var arow=a.audio_items[i],aclip=this._placeAudioItem(seq,arow,itemMap);audioReadback.push(this._certifyPlacedClip(aclip,arow,'AUDIO',Number(data.project.fps)));ap++;}report.stage=stage;report.audio_items_placed=ap;report.audio_timeline_readback=audioReadback;if(reportPath)this._writeJSON(reportPath,report);
      stage='ADD_MARKERS';report.marker_count=this._addMarkers(seq,a.markers||[]);report.stage=stage;if(reportPath)this._writeJSON(reportPath,report);

      // Motion and typography are physically baked into the animated 1920x1080 Scene clips.
      // Premiere MUST NOT write ComponentParam keyframes to still PNGs on this path.
      stage='CERTIFY_PRE_RENDERED_MOTION';report.stage=stage;report.pre_rendered_motion_events_certified=report.pre_rendered_motion_events_total;report.selective_text_events_certified=report.selective_text_events_total;report.premiere_keyframes_written=0;if(reportPath)this._writeJSON(reportPath,report);

      stage='PHYSICAL_TIMELINE_QA';report.stage=stage;report.actual_video_tracks=seq.videoTracks.numTracks;report.actual_audio_tracks=seq.audioTracks.numTracks;report.master_sequence_found=!!this._findSequence(String(a.sequence_name||'HEXA_V31_MASTER'));if(!report.master_sequence_found)throw new Error('Master sequence disappeared after native assembly');if(vp!==vrows.length||videoReadback.length!==vrows.length)throw new Error('Video placement/readback parity mismatch');if(ap!==(a.audio_items||[]).length||audioReadback.length!==(a.audio_items||[]).length)throw new Error('Audio placement/readback parity mismatch');var timelineTol=Math.max(0.02,1/Math.max(1,Number(data.project.fps)||30)+0.01),cursor=0;for(i=0;i<vrows.length;i++){var vst=Number(vrows[i].start_seconds),ven=Number(vrows[i].end_seconds);if(i===0&&Math.abs(vst)>timelineTol)throw new Error('Animated media timeline must begin at zero; first_start='+vst);if(i>0&&Math.abs(vst-cursor)>timelineTol)throw new Error('Animated media continuity mismatch before '+String(vrows[i].clip_display_name||'')+': start='+vst+' previous_end='+cursor);if(!(ven>vst))throw new Error('Animated media non-positive interval for '+String(vrows[i].clip_display_name||''));cursor=ven;}if(audioReadback.length){var audioEnd=Number((a.audio_items||[])[audioReadback.length-1].end_seconds);if(Math.abs(cursor-audioEnd)>timelineTol)throw new Error('Video/audio timeline end mismatch: video_end='+cursor+' audio_end='+audioEnd);}report.timeline_readback_pass=true;report.video_timeline_readback_verified=videoReadback.length;report.audio_timeline_readback_verified=audioReadback.length;report.timeline_duration_seconds=cursor;report.timeline_tolerance_seconds=timelineTol;if(reportPath)this._writeJSON(reportPath,report);
      stage='SAVE_PROJECT';report.stage=stage;var savePath=String(a.project_save_path||'');if(savePath){var sf=new File(savePath);try{if(!sf.parent.exists)sf.parent.create();var sv=app.project.saveAs(sf.fsName);if(sv===false)throw new Error('app.project.saveAs returned false');try{$.sleep(200);}catch(_slp){}var rf=new File(sf.fsName);if(!rf.exists||Number(rf.length)<4096)throw new Error('Premiere project physical readback failed: '+sf.fsName);report.project_saved_path=rf.fsName;report.project_saved_bytes=Number(rf.length);}catch(se){throw new Error('Unable to save Premiere project: '+se.toString());}}if(reportPath)this._writeJSON(reportPath,report);
      stage='RESET_PLAYHEAD';report.stage=stage;try{if(seq.setPlayerPosition)seq.setPlayerPosition('0');report.playhead_reset_to_start=true;}catch(_ph){report.playhead_reset_to_start=false;report.playhead_reset_warning=_ph.toString();}if(reportPath)this._writeJSON(reportPath,report);
      report.status='PASS';report.stage='COMPLETE';report.completed_at=(new Date()).toUTCString();if(reportPath)this._writeJSON(reportPath,report);
      return 'PASS: version=31.0.25 animated_scenes='+vp+'/'+vrows.length+' audio='+ap+'/'+(a.audio_items||[]).length+' pre_rendered_motion='+report.pre_rendered_motion_events_certified+'/'+report.pre_rendered_motion_events_total+' text='+report.selective_text_events_certified+'/'+report.selective_text_events_total+' premiere_keyframes=0 project='+String(report.project_saved_path||'')+' engine_mp4='+String(report.engine_final_mp4_path||'');
    }catch(e){report.status='FAIL';report.stage=stage;report.error=e.toString();report.completed_at=(new Date()).toUTCString();if(reportPath)this._writeJSON(reportPath,report);return 'FAIL: stage='+stage+' reason='+e.toString()+(reportPath?' report='+reportPath:'');}
  },

  // Kept only so stale callers receive a precise safety failure instead of opening
  // the old XML path that produced Premiere's damaged-project dialog in V20.0.3.
  importAndApply:function(xmlPath,mapPath){return 'FAIL: XML_IMPORT_DISABLED_IN_V31_0_1; use assembleAndApply(editMap)';}
};

