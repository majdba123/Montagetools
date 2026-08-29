from __future__ import annotations
import argparse, json, pathlib, sys
from .pipeline import build, BuildFailure
from .package_io import open_and_validate
from .util import ensure_dir, read_json
from .production_cert import certify_production


def main(argv=None):
    p=argparse.ArgumentParser(prog='hexa-v31')
    sub=p.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('build'); b.add_argument('--package',required=True); b.add_argument('--voice',required=True); b.add_argument('--work-root'); b.add_argument('--extension-root')
    v=sub.add_parser('validate-package'); v.add_argument('--package',required=True); v.add_argument('--cache-root',default=str(pathlib.Path.cwd()/'.hexa_validate'))
    c=sub.add_parser('certify-production'); c.add_argument('--mp4',required=True); c.add_argument('--expected-duration',type=float,required=True); c.add_argument('--extension-root',required=True); c.add_argument('--out-dir',required=True); c.add_argument('--runtime-config')
    args=p.parse_args(argv)
    try:
        if args.cmd=='build':
            r=build(args.package,args.voice,args.work_root,args.extension_root,echo=True); print('HEXA_V31_RESULT_JSON='+json.dumps(r,ensure_ascii=False)); return 0
        if args.cmd=='validate-package':
            x=open_and_validate(args.package,ensure_dir(args.cache_root)); print(json.dumps({'status':'PASS','project_id':x.plan.get('project_id'),'scene_count':len(x.scenes)},ensure_ascii=False)); return 0
        if args.cmd=='certify-production':
            cfg={}
            if args.runtime_config and pathlib.Path(args.runtime_config).is_file(): cfg=read_json(args.runtime_config)
            r=certify_production(args.mp4,args.expected_duration,args.extension_root,args.out_dir,cfg)
            print('HEXA_V31_PRODUCTION_CERT_JSON='+json.dumps(r,ensure_ascii=False))
            return 0 if r.get('status') in ('PASS','REVIEW_REQUIRED') else 3
    except BuildFailure as e:
        if e.payload: print('HEXA_V31_FAILURE_JSON='+json.dumps(e.payload,ensure_ascii=False),file=sys.stderr)
        print('HEXA_V31_FATAL='+str(e),file=sys.stderr); return 2
    except Exception as e:
        print('HEXA_V31_FATAL='+str(e),file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
