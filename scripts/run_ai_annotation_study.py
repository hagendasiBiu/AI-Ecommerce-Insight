"""Explicit paid AI labeling of 300 tasks; no human labels or approvals are fabricated."""
from pathlib import Path
import argparse
from datetime import datetime,timezone
import hashlib
import json
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ai_annotation import load_tasks, model_input, summarize, consistency, validate_saved
from src.review_analysis import validate_batch_response
from src.workflow_runner import run_recorded

OUT=ROOT/'data/processed/ai_annotation_study.json'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.writing')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--estimated-new-cost-cap',type=float,default=10)
    args=parser.parse_args()
    tasks=load_tasks(ROOT)
    workflow_hash=hashlib.sha256((ROOT/'dify/review_analysis_workflow.yml').read_bytes()).hexdigest()
    task_hash=hashlib.sha256(json.dumps([model_input(t) for t in tasks],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if not args.execute:
        print(json.dumps({'tasks':len(tasks),'paid_calls_made':0,'mode':'AI labels, not human gold',
            'new_cost_estimate_cap_cny':args.estimated_new_cost_cap,'task_sha256':task_hash}))
        return
    if OUT.exists():
        study=json.loads(OUT.read_text(encoding='utf-8'))
        if study['workflow_sha256']!=workflow_hash or study['task_sha256']!=task_hash:
            raise ValueError('Existing study uses a different workflow or task set')
    else:
        study={'workflow_sha256':workflow_hash,'task_sha256':task_hash,'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'protocol':'ai-annotation-study-v1','annotation_origin':'AI','human_review_status':'not_reviewed',
            'user_authorized_ai_only':True,'independent_human_gold':False,'items':{},'runs':[],
            'repeat_items':{},'execution_seconds':0.0}
        # Reuse verified existing development outputs; do not overwrite actual human records.
        old=ROOT/'data/processed/phase4_review_results.json'
        prior=json.loads(old.read_text(encoding='utf-8'))['results'] if old.exists() else []
        byid={r['review_id']:r for r in prior}
        for task in tasks:
            if task['review_id'] in byid:
                item=validate_saved(byid[task['review_id']],task)
                if item['status']=='validated':
                    study['items'][task['review_id']]=item|{'annotation_origin':'AI','provenance':'phase4_record_reused'}
    started=time.perf_counter()
    previous_elapsed=study['execution_seconds']
    def persist():
        study['execution_seconds']=previous_elapsed+time.perf_counter()-started
        study['summary']=summarize(ROOT,tasks,study['items'],study['runs'],study['execution_seconds'])
        write(OUT,study)
        write(ROOT/'reports/phase6_ai_study_summary.json',study['summary'])
    def request_batch(batch,purpose,version):
        used=sum(r.get('total_tokens') or 0 for r in study['runs'] if not r.get('reused'))*8/1_000_000
        if used+0.8>args.estimated_new_cost_cap:
            raise RuntimeError('Estimated cost cap reached; no additional request submitted')
        response,reused=run_recorded(ROOT,{'reviews_json':json.dumps([model_input(t) for t in batch],ensure_ascii=False)},
            'DIFY_API_KEY',version,purpose)
        receipt={k:response.get(k) for k in ['workflow_run_id','status','total_tokens','client_elapsed_seconds','http_attempts','request_digest']}
        receipt.update(reused=reused,purpose=purpose,review_count=len(batch))
        study['runs'].append(receipt)
        # Persist the receipt first, even if the response cannot be interpreted.
        persist()
        if response.get('status')!='succeeded':
            return [{'review_id':t['review_id'],'status':'workflow_item_failed','analysis':None} for t in batch]
        return validate_batch_response(response['outputs'],[model_input(t) for t in batch])
    try:
        remaining=[t for t in tasks if t['review_id'] not in study['items']]
        for offset in range(0,len(remaining),5):
            batch=remaining[offset:offset+5]
            results=request_batch(batch,'phase6_ai_annotation',workflow_hash+':restored-app-max-tokens-2048')
            for result in results:
                study['items'][result['review_id']]=result|{'annotation_origin':'AI','provenance':'real_dify_workflow'}
            persist()
            print(json.dumps({'phase':'annotation','completed':study['summary']['completed_ai_annotations'],
                'recorded':len(study['items']),'tasks':300,'new_tokens':study['summary']['new_total_tokens']},ensure_ascii=False),flush=True)
        # Pre-fixed development positions only; source labels are noisy and are not gold.
        repeat_tasks=[t for t in tasks if t['split']=='prompt_dev' and t['number'] in [1,2,3,4,5,101,102,103,104,105]]
        repeat_pending=[t for t in repeat_tasks if t['review_id'] not in study['repeat_items']]
        for offset in range(0,len(repeat_pending),5):
            batch=repeat_pending[offset:offset+5]
            results=request_batch(batch,'phase6_repeat_stability',workflow_hash+':restored-app-max-tokens-2048:repeat-stability-v1')
            study['repeat_items'].update({r['review_id']:r for r in results}); persist()
        study['consistency']=consistency({t['review_id']:study['items'][t['review_id']] for t in repeat_tasks},study['repeat_items'])
    finally:
        persist()
    study['summary']=summarize(ROOT,tasks,study['items'],study['runs'],study['execution_seconds'])
    write(OUT,study)
    write(ROOT/'reports/phase6_ai_study_summary.json',study['summary']|{'consistency':study.get('consistency')})
    print(json.dumps({'finished':True,'summary':study['summary'],'consistency':study.get('consistency')},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
