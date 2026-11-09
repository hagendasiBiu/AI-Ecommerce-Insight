"""Read-only progress audit. Does not output texts, answers, annotator names or keys."""
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evaluation import AnnotationStore


def main():
    store=AnnotationStore(ROOT)
    result={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'status':'in_progress',
            'splits':{},'quality_metrics_status':'pending_independent_human_gold',
            'remaining_work':['complete_development_annotations_and_rules',
                'freeze_independent_gold_and_evaluate','measure_actual_workflow_times','record_demo_and_finalize_materials']}
    for split in ['prompt_dev','heldout_test']:
        path=ROOT/'data/sample'/('annotation_'+split+'.csv')
        if not path.exists():
            result['splits'][split]={'status':'local_tasks_missing'}
            continue
        # Progress methods may read task text internally; only aggregate counts leave this script.
        tasks=store.tasks(split); saved=store.records(split)
        relevant=[saved[t['review_id']] for t in tasks if t['review_id'] in saved]
        result['splits'][split]=store.progress(split)|{
            'ai_assistance_disclosed_count':sum('AI' in r.get('notes','') for r in relevant),
            'remaining':len(tasks)-len(relevant)}
    result['timing_note']='AI-assisted entries and unverified active-page times are not a pure manual baseline.'
    output=ROOT/'reports/phase6_annotation_progress.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
