"""Finalize AI coverage while preserving immutable first-pass evidence and human records."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ai_annotation import load_tasks, summarize, model_input
from src.evaluation import AnnotationStore, canonical
from src.review_analysis import contract


def main():
    path=ROOT/'data/processed/ai_annotation_study.json'
    study=json.loads(path.read_text(encoding='utf-8'))
    tasks=load_tasks(ROOT); by_position={(t['split'],t['number']):t for t in tasks}
    human=AnnotationStore(ROOT)
    before=hashlib.sha256(canonical({s:human.records(s) for s in ['prompt_dev','heldout_test']}).encode()).hexdigest()
    first_pass=study.get('first_pass_items',study['items'])
    study['first_pass_items']=first_pass
    study['first_pass_summary']=summarize(ROOT,tasks,first_pass,study['runs'],study['execution_seconds'])
    # Copy envelopes; original failures are retained and never rewritten as Dify successes.
    final=dict(first_pass)
    repairs=json.loads((ROOT/'data/processed/codex_ai_repairs.json').read_text(encoding='utf-8'))
    repaired=[]
    for value in repairs['repairs']:
        task=by_position[(value['split'],value['number'])]
        rid=task['review_id']
        if first_pass[rid]['status']=='validated':
            raise ValueError('Supplemental annotation may only fill a failed first-pass item')
        raw={k:v for k,v in value.items() if k in contract.FIELDS}|{'review_id':rid}
        analysis=contract.validate_output(raw,model_input(task))
        final[rid]={'review_id':rid,'status':'validated','analysis':analysis,'annotation_origin':'AI',
            'provenance':'codex_supplemental_annotation','human_review_status':'not_reviewed',
            'first_pass_error_code':first_pass[rid].get('error_code')}
        repaired.append(rid)
    summary=summarize(ROOT,tasks,final,study['runs'],study['execution_seconds'])
    summary.update(first_pass_contract_pass_rate=study['first_pass_summary']['contract_pass_rate'],
        first_pass_validated_count=study['first_pass_summary']['completed_ai_annotations'],
        codex_supplemental_count=len(repaired),consistency_first_pass=study.get('consistency'),
        supplemental_note='补充结果由 Codex AI 根据原文填写并做契约校验，不是人工复核，也不是 Dify 首次成功。',
        ai_coverage_rate=summary.pop('contract_pass_rate'))
    after=hashlib.sha256(canonical({s:human.records(s) for s in ['prompt_dev','heldout_test']}).encode()).hexdigest()
    if after!=before: raise ValueError('Human records unexpectedly changed')
    summary['human_records_unchanged']=True
    result={'mode':'AI-only deliverable','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'task_sha256':study['task_sha256'],'workflow_sha256':study['workflow_sha256'],
        'human_records_sha256':before,'summary':summary,'items':final}
    (ROOT/'data/processed/ai_annotations_final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    path.write_text(json.dumps(study,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for task in tasks:
        item=final[task['review_id']]; a=item.get('analysis') or {}
        rows.append({**task,'annotation_origin':item.get('provenance','AI'),
            'scope_status':a.get('scope_status'),'sentiment':a.get('sentiment'),
            'issue_labels_json':json.dumps([i['label'] for i in a.get('issues',[])],ensure_ascii=False),
            'evidence_json':json.dumps(a.get('issues',[]),ensure_ascii=False),
            'user_need':a.get('user_need'),'issue_summary':a.get('issue_summary'),
            'needs_review':a.get('needs_review'),'human_review_status':'not_reviewed'})
    pd.DataFrame(rows).to_csv(ROOT/'data/processed/ai_annotations_300.csv',index=False,encoding='utf-8-sig')
    (ROOT/'reports/phase6_ai_study_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ai_annotations':summary['completed_ai_annotations'],'supplemental':len(repaired),
        'first_pass':summary['first_pass_validated_count'],'human_records_unchanged':True},ensure_ascii=False))


if __name__=='__main__': main()
