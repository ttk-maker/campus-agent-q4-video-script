"""Run difficult claims and timing limits with honest model/review labels."""
import argparse
from pathlib import Path
import tempfile
from scripts.evaluate import dump
from src.agent import Agent
from src.models import MockModel,HTTPModel
from src.review import ReviewModel
from src.scenarios import scenario,draft
from src.store import Store

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['review','real'],default='review')
    p.add_argument('--output',default='examples/hardening/review')
    p.add_argument('--case',choices=['english_boundary','impossible_duration']);args=p.parse_args()
    pairs={'english_boundary':('We are now here.','We are nowhere.'),'question':('支持字幕？','支持字幕。'),
           'clause_boundary':('不支持字幕，导出。','不支持，字幕导出。'),'unit_exponent':('面积2m²。','面积2m2。'),
           'decimal':('数值为1.0。','数值为10。'),'valid':('支持字幕。','支持 字幕！')}
    names=['english_boundary','impossible_duration'] if args.mode=='real' else list(pairs)+['impossible_duration','transition_overrun']
    if args.case:names=[args.case]
    report={'mode':args.mode,'cases':[],'passed':True}
    for name in names:
        with tempfile.TemporaryDirectory() as temp:
            payload=scenario('normal');req,cat=payload['request'],payload['catalog'];req['request_id']=name
            script=draft((10,9,9))
            if name in pairs:
                fact,claim=pairs[name];cat['materials'][0]['facts'][0]['text']=fact
                for s in script['scenes']:s['voiceover']=fact
                script['scenes'][0]['voiceover']=claim
            if name=='impossible_duration':req['target_seconds']=1
            if name=='transition_overrun':req['target_seconds']=28;cat['rules']['transition_seconds']=.5
            req['initial_script']=script;payload['mode']=args.mode
            folder=Path(args.output)/name;dump(folder/'input.json',payload)
            model=HTTPModel() if args.mode=='real' else ReviewModel(['字幕'])
            agent=Agent(model,Store(Path(temp)/'state.db'),cat,16);r=agent.run(req)
            checks={'correct_status':r['status']==('completed' if name=='valid' or (args.mode=='real' and name=='english_boundary') else 'cannot_satisfy')}
            if args.mode=='review':checks['no_silent_rewrite']=r['script']==script
            if name=='english_boundary' and args.mode=='real':
                checks['observed_risk']=any(s['action']['tool']=='check_rules' and s['observation'].get('passed') is False for s in agent.trace)
                checks['fixed_claim']=r['rules_check'] is not None and r['rules_check']['passed']
            if name=='impossible_duration':checks['no_fake_ready']=r['script_status']=='unverified'
            dump(folder/'run.json',{'output':r,'trace':agent.trace,'mode':model.mode})
            case={'name':name,'checks':checks,'passed':all(checks.values())};report['cases'].append(case);report['passed'] &= case['passed']
            dump(Path(args.output)/'report.json',report);print(name,r['status'],case['passed'],flush=True)
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
