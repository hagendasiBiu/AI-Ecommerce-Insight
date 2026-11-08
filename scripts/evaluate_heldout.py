"""Local scoring only. Never calls a model or prints heldout texts/labels."""
from pathlib import Path
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evaluation import AnnotationStore, evaluate, sha
from src.review_analysis import validate_batch_response


def main():
    store=AnnotationStore(ROOT)
    frozen=store.freeze_record('heldout_test')
    if not frozen:
        print(json.dumps({'status':'pending_human_gold','progress':store.progress('heldout_test')},ensure_ascii=False))
        return
    tasks=store.tasks('heldout_test'); saved=store.records('heldout_test'); gold=[saved[t['review_id']] for t in tasks]
    if sha(gold)!=frozen['gold_sha256'] or sha(tasks)!=frozen['task_sha256']:
        raise SystemExit('Frozen gold or tasks changed. Stop; do not silently rescore.')
    for path,digest in frozen['files'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:
            raise SystemExit('Frozen evaluation workflow/rules changed. Stop; do not tune on test results.')
    path=ROOT/'data/processed/heldout_predictions.json'
    if not path.exists():
        print('Frozen gold ready; fixed heldout predictions not recorded. No API request made.')
        return
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload.get('gold_freeze_sha256')!=sha(frozen):
        raise SystemExit('Prediction manifest is not bound to this gold freeze.')
    reviews=[{k:t[k] for k in ['review_id','review_text']}|{'language':'zh','product_category':'clothing'} for t in tasks]
    predictions=payload['predictions']
    byid={p['review_id']:p for p in predictions}
    if len(byid)!=len(predictions) or set(byid)!={r['review_id'] for r in reviews}:
        raise SystemExit('Prediction ID set mismatch.')
    checked=validate_batch_response({'results':[byid[r['review_id']] if byid[r['review_id']].get('status')!='workflow_item_failed' else None for r in reviews]},reviews)
    result=evaluate(gold,checked)
    result.update(gold_sha256=frozen['gold_sha256'],predictions_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    target=ROOT/'reports/heldout_evaluation.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'scored','n':result['n'],'report':str(target)},ensure_ascii=False))


if __name__=='__main__': main()
