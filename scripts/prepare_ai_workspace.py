"""Create a separate AI research workspace; never overwrite the approved 20-row case."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ai_annotation import load_tasks,model_input
from src.app_service import AppService


def main():
    final=json.loads((ROOT/'data/processed/ai_annotations_final.json').read_text(encoding='utf-8'))
    service=AppService(ROOT)
    tasks=load_tasks(ROOT)
    wid=service.create('AI 批量研究 · 300 条（未经人工复核）',[model_input(t) for t in tasks],
        {'kind':'user_authorized_ai_only_study','former_holdout_repurposed':True})
    service.save_analyses(wid,list(final['items'].values()))
    evidence=service.build_evidence(wid)
    service.put(wid,'ai_study_summary',final['summary'])
    final['workspace_id']=wid
    (ROOT/'data/processed/ai_annotations_final.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'workspace_id':wid,'analyzed':evidence['requested_reviews'],
        'eligible':evidence['validated_in_scope_known_sentiment_reviews'],'issues':len(evidence['issues']),
        'approved_plans':sum(d['status']=='approved' for d in service.drafts(wid))},ensure_ascii=False))


if __name__=='__main__': main()
