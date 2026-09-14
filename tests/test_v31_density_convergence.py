from unittest.mock import patch
from hexa_v31.planning.final_density_recovery import converge_final_density


def run(step, initial=0, bound=32):
    calls=[]
    def recover(plan, fps):
        old=plan['events'][0]['x'];new=step(old)
        plan['events'][0]['x']=new
        return {'repaired_event_ids':['actor'] if old!=new else []}
    def certify(plan, fps):
        calls.append(plan['events'][0]['x'])
        return plan
    def report(plan):
        return {'hard_under_density_cards': [] if plan['events'][0]['x']==5 else ['sentence']}
    with patch('hexa_v31.planning.final_density_recovery.recover_final_density',recover), patch('hexa_v31.planning.final_density_recovery.build_visual_density_report',report):
        result=converge_final_density({'events':[{'x':initial}]},fps=30,recertify=certify,restore_metadata=lambda p:None,max_iterations=bound)
    return result,calls

r,c=run(lambda x:min(5,x+1));assert r[2]['reason']=='PASS' and len(c)==5
r,c=run(lambda x:x);assert r[2]['reason']=='NO_PROGRESS' and not c
r,c=run(lambda x:1-x);assert r[2]['reason']=='REPEATED_STATE' and len(c)==2
r,c=run(lambda x:x+1,bound=7);assert r[2]['reason']=='SAFETY_BOUND' and len(c)==7
print('density convergence PASS')
