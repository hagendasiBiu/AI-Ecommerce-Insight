"""AI annotation artifacts are separate from human gold and approval records."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import pandas as pd
from src.evaluation import AnnotationStore, canonical
from src.review_analysis import validate_batch_response


def load_tasks(root):
    store=AnnotationStore(root)
    tasks=[]
    for split in ['prompt_dev','heldout_test']:
        for number,task in enumerate(store.tasks(split),1):
            tasks.append({'split':split,'number':number,'review_id':task['review_id'],
                'review_text':task['review_text'],'language':'zh','product_category':'clothing'})
    ids=[t['review_id'] for t in tasks]
    if len(tasks)!=300 or len(ids)!=len(set(ids)):
        raise ValueError('Expected the original fixed 300 unique tasks')
    return tasks


def model_input(task):
    return {k:task[k] for k in ['review_id','review_text','language','product_category']}


def validate_saved(record,task):
    return validate_batch_response({'results':[record]},[model_input(task)])[0]


def summarize(root,tasks,items,run_records,elapsed):
    """Source-label agreement is weak-label agreement, never independent accuracy."""
    aligned=[items.get(t['review_id'],{'status':'not_completed','analysis':None}) for t in tasks]
    valid=[r.get('status')=='validated' for r in aligned]
    sentiments=Counter((r.get('analysis') or {}).get('sentiment','failed') for r in aligned)
    issue_counts=Counter(i['label'] for r in aligned if r.get('status')=='validated' for i in r['analysis']['issues'])
    source=pd.read_csv(Path(root)/'data/processed/split_manifest_private.csv',usecols=['review_id','source_label'])
    source_labels=dict(zip(source.review_id,source.source_label))
    matrix={name:{s:0 for s in ['positive','negative','neutral','mixed','unknown','failed']}
            for name in ['source_positive','source_negative']}
    agreements=0
    for task,result in zip(tasks,aligned):
        raw=source_labels.get(task['review_id'])
        if raw not in (0,1): raise ValueError('Missing weak source label')
        name='source_positive' if raw==1 else 'source_negative'
        sentiment=(result.get('analysis') or {}).get('sentiment','failed')
        matrix[name][sentiment]+=1
        agreements+=sentiment==('positive' if raw==1 else 'negative')
    new_runs=[r for r in run_records if not r.get('reused')]
    total_tokens=sum(r.get('total_tokens') or 0 for r in new_runs)
    return {'version':'ai-annotation-study-v1','mode':'ai_only_annotation_not_human_gold',
        'task_count':len(tasks),'completed_ai_annotations':sum(valid),'failed_or_pending':len(tasks)-sum(valid),
        'contract_pass_rate':sum(valid)/len(tasks),'sentiment_counts':dict(sentiments),
        'issue_counts':dict(issue_counts),'ai_flagged_for_review':sum(bool((r.get('analysis') or {}).get('needs_review')) for r in aligned),
        'source_label_agreement':{'agreement_count':agreements,'denominator':len(tasks),
            'agreement_rate':agreements/len(tasks),'matrix':matrix,
            'interpretation':'原语料弱标签一致率，不是独立人工准确率；mixed/neutral/unknown/失败均不当作一致。'},
        'new_run_count':len(new_runs),'new_total_tokens':total_tokens,'batch_execution_wall_seconds':elapsed,
        'sum_new_request_seconds':sum(r.get('client_elapsed_seconds') or 0 for r in new_runs),
        'conservative_model_cost_estimate_cny':total_tokens*8/1_000_000,
        'cost_note':'按全部 tokens 均以高峰输出单价 8 元/百万估算；不是账单，不包含此前费用或平台服务费用。',
        'independent_human_accuracy':None,'independent_human_macro_f1':None,'manual_efficiency_gain':None,
        'limitations':['用户改为 AI 代标，原 100 条保留集不再作为独立人工真值测试',
            '前 5 条用户复核记录独立保留，不覆盖，也不外推为 300 条人工审核',
            '契约通过率只检查格式、枚举和原文引用，不证明语义判断正确',
            '源情感标签有噪声且抽样平衡，不能外推平台总体表现',
            '缺少独立人工质量基准及完整人工时间，不能报告人工提效比例',
            '来源平台、采集时间和许可未确认，原始评论与 AI 逐条结果只保留本地']}


def consistency(first,second):
    if set(first)!=set(second) or not first:
        raise ValueError('Consistency runs must use identical nonempty ID sets')
    matched_sentiment=matched_labels=matched_scope=valid_pair=0
    for rid in first:
        a,b=first[rid],second[rid]
        if a.get('status')!='validated' or b.get('status')!='validated': continue
        valid_pair+=1
        a,b=a['analysis'],b['analysis']
        matched_sentiment+=a['sentiment']==b['sentiment']
        matched_scope+=a['scope_status']==b['scope_status']
        matched_labels+={i['label'] for i in a['issues']}=={i['label'] for i in b['issues']}
    n=len(first)
    return {'n':n,'valid_pairs':valid_pair,'sentiment_exact_agreement':matched_sentiment/n,
        'scope_exact_agreement':matched_scope/n,'issue_set_exact_agreement':matched_labels/n,
        'interpretation':'同一模型重复运行稳定性，不是准确率；失败保留在分母。'}
