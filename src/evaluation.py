"""Blind human annotations and deterministic evaluation. Never creates gold labels with AI."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import sqlite3
import pandas as pd
from src.review_analysis import contract

SPLITS = {'prompt_dev': 'annotation_prompt_dev.csv', 'heldout_test': 'annotation_heldout_test.csv'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class AnnotationStore:
    def __init__(self, root, db_path=None):
        self.root = Path(root)
        self.path = Path(db_path) if db_path else self.root/'data/processed/human_annotations.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS annotations (
                split TEXT, review_id TEXT, body TEXT NOT NULL,
                PRIMARY KEY(split,review_id));
              CREATE TABLE IF NOT EXISTS annotation_events (
                id INTEGER PRIMARY KEY, split TEXT, review_id TEXT, body TEXT, created_at TEXT);
              CREATE TABLE IF NOT EXISTS gold_freezes (
                split TEXT PRIMARY KEY, body TEXT NOT NULL);
            ''')
            db.commit()

    def tasks(self, split):
        if split not in SPLITS:
            raise ValueError('Unknown annotation split')
        # Callers must not log heldout text. Only the human-facing UI displays it.
        frame = pd.read_csv(self.root/'data/sample'/SPLITS[split], dtype=str, keep_default_na=False)
        if frame.review_id.duplicated().any():
            raise ValueError('Duplicate task IDs')
        return frame.to_dict('records')

    def records(self, split):
        with closing(sqlite3.connect(self.path)) as db:
            return {r[0]: json.loads(r[1]) for r in db.execute(
                'SELECT review_id,body FROM annotations WHERE split=?', (split,))}

    def progress(self, split):
        tasks = self.tasks(split)
        saved = self.records(split)
        current = [saved[t['review_id']] for t in tasks if t['review_id'] in saved]
        return {'total': len(tasks), 'completed': len(current),
                'reviewed': sum(r['review_status']=='approved' for r in current),
                'annotation_seconds': sum(r['annotation_seconds'] for r in current)}

    def freeze_record(self, split):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT body FROM gold_freezes WHERE split=?', (split,)).fetchone()
            return json.loads(row[0]) if row else None

    def save(self, split, review_id, body):
        if self.freeze_record(split):
            raise ValueError('测试答案已冻结；不得继续修改后重复调参。')
        task = next((r for r in self.tasks(split) if r['review_id']==review_id), None)
        if not task:
            raise ValueError('Review is not a member of this split')
        value = dict(body)
        if value.get('scope_status') not in contract.SCOPES or value.get('sentiment') not in contract.SENTIMENTS:
            raise ValueError('请填写范围和情感。')
        labels, evidence = value.get('issue_labels'), value.get('evidence')
        if (not isinstance(labels,list) or any(not isinstance(i,str) for i in labels)
                or len(labels)!=len(set(labels)) or not set(labels)<=contract.ALLOWED_LABELS):
            raise ValueError('问题标签无效或重复。')
        if not isinstance(evidence,list) or len(evidence)!=len(labels):
            raise ValueError('每个问题标签需要一条原文证据。')
        seen = set()
        for item in evidence:
            if not isinstance(item,dict) or set(item)!={'label','quote'}:
                raise ValueError('证据格式应为 label、quote。')
            label, quote = item['label'], item['quote']
            if label not in labels or label in seen or not isinstance(quote,str) or not quote.strip() or quote not in task['review_text']:
                raise ValueError('证据必须逐字出现在当前原文中，且与标签一一对应。')
            seen.add(label)
        if value['sentiment']=='positive' and labels:
            raise ValueError('正向评论不填写负向问题标签；正负并存请核查 mixed。')
        for key in ['annotator_id','user_need','notes']:
            if not isinstance(value.get(key),str):
                raise ValueError('Missing annotation string field')
        if not value['annotator_id'].strip():
            raise ValueError('请填写真实标注者代号。')
        seconds = value.get('annotation_seconds')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:
            raise ValueError('请先开始计时并完成人工标注。')
        # Every edit invalidates a prior review; approval is a separate explicit human step.
        value.update(review_id=review_id, review_status='pending', reviewer_id='',
                     updated_at=datetime.now(timezone.utc).isoformat())
        encoded = canonical(value)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM gold_freezes WHERE split=?',(split,)).fetchone():
                raise ValueError('测试答案已冻结。')
            db.execute('INSERT OR REPLACE INTO annotations VALUES (?,?,?)',(split,review_id,encoded))
            db.execute('INSERT INTO annotation_events(split,review_id,body,created_at) VALUES (?,?,?,?)',
                       (split,review_id,encoded,value['updated_at']))
            db.commit()

    def approve(self, split, review_id, reviewer_id):
        if not reviewer_id.strip():
            raise ValueError('请填写真实复核者代号；单人复核应如实填写同一代号。')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM gold_freezes WHERE split=?',(split,)).fetchone():
                raise ValueError('测试答案已冻结。')
            row = db.execute('SELECT body FROM annotations WHERE split=? AND review_id=?',(split,review_id)).fetchone()
            if not row:
                raise ValueError('请先保存人工标注。')
            value=json.loads(row[0]); value.update(review_status='approved',reviewer_id=reviewer_id.strip())
            encoded=canonical(value)
            db.execute('UPDATE annotations SET body=? WHERE split=? AND review_id=?',(encoded,split,review_id))
            db.execute('INSERT INTO annotation_events(split,review_id,body,created_at) VALUES (?,?,?,?)',
                       (split,review_id,encoded,datetime.now(timezone.utc).isoformat()))
            db.commit()

    def freeze(self, actor):
        if not actor.strip():
            raise ValueError('冻结操作需要真实操作人。')
        split='heldout_test'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body FROM gold_freezes WHERE split=?',(split,)).fetchone()
            if old:
                return json.loads(old[0])
            tasks=self.tasks(split)
            saved={r[0]:json.loads(r[1]) for r in db.execute('SELECT review_id,body FROM annotations WHERE split=?',(split,))}
            if len(tasks)!=100 or any(t['review_id'] not in saved or saved[t['review_id']]['review_status']!='approved' for t in tasks):
                raise ValueError('必须先完成固定 100 条独立测试评论的人工标注与复核。')
            gold=[saved[t['review_id']] for t in tasks]
            paths=['docs/annotation_guide.md','dify/review_analysis_workflow.yml','dify/nodes/validate_review.py']
            files={p:hashlib.sha256((self.root/p).read_bytes()).hexdigest() for p in paths}
            result={'split':split,'count':100,'gold_sha256':sha(gold),'task_sha256':sha(tasks),
                    'protocol':'evaluation-v1','files':files,'actor':actor.strip(),
                    'created_at':datetime.now(timezone.utc).isoformat()}
            db.execute('INSERT INTO gold_freezes VALUES (?,?)',(split,canonical(result))); db.commit()
            return result


def classification_scores(expected, predicted, labels):
    if not expected or len(expected)!=len(predicted):
        raise ValueError('Evaluation vectors must be nonempty and aligned')
    details=[]
    for label in labels:
        tp=sum(a==label and b==label for a,b in zip(expected,predicted))
        fp=sum(a!=label and b==label for a,b in zip(expected,predicted))
        fn=sum(a==label and b!=label for a,b in zip(expected,predicted))
        p=tp/(tp+fp) if tp+fp else 0.0
        r=tp/(tp+fn) if tp+fn else 0.0
        details.append({'label':label,'support':sum(a==label for a in expected),
                        'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.0})
    return {'n':len(expected),'accuracy':sum(a==b for a,b in zip(expected,predicted))/len(expected),
            'macro_f1':sum(r['f1'] for r in details)/len(details),'per_class':details,
            'zero_division':0,'macro_denominator':len(labels)}


def evaluate(gold, predictions):
    """All fixed task IDs stay in denominator, including failed model items."""
    ids=[r['review_id'] for r in gold]
    pred_ids=[r['review_id'] for r in predictions]
    if not ids or len(ids)!=len(set(ids)) or len(pred_ids)!=len(set(pred_ids)) or set(ids)!=set(pred_ids):
        raise ValueError('Missing, duplicate or extra prediction IDs')
    if any(g.get('review_status')!='approved' for g in gold):
        raise ValueError('Gold is not human reviewed')
    byid={p['review_id']:p for p in predictions}
    aligned=[byid[i] for i in ids]
    valid=[p.get('status')=='validated' and isinstance(p.get('analysis'),dict) for p in aligned]
    expected=[set(g['issue_labels']) for g in gold]
    actual=[{i['label'] for i in p['analysis']['issues']} if ok else set() for p,ok in zip(aligned,valid)]
    if any(not s<=contract.ALLOWED_LABELS for s in actual):
        raise ValueError('Unknown prediction issue label')
    issue_rows=[]
    for label in sorted(contract.ALLOWED_LABELS):
        # Failed items also count as a missed decision on gold-negative/empty-label tasks.
        a=[label if label in s else '__absent__' for s in expected]
        b=[label if label in s else '__absent__' for s in actual]
        issue_rows.append(classification_scores(a,b,[label])['per_class'][0])
    tp=sum(len(a&b) for a,b in zip(expected,actual))
    fp=sum(len(b-a) for a,b in zip(expected,actual))
    fn=sum(len(a-b) for a,b in zip(expected,actual))
    precision=tp/(tp+fp) if tp+fp else 0.0; recall=tp/(tp+fn) if tp+fn else 0.0
    result={'n':len(gold),'validated_count':sum(valid),'failed_count':len(gold)-sum(valid),
            'contract_pass_rate':sum(valid)/len(gold),'evaluation_version':'evaluation-v1',
            'sentiment':classification_scores([g['sentiment'] for g in gold],
                [p['analysis']['sentiment'] if ok else '__failed__' for p,ok in zip(aligned,valid)],sorted(contract.SENTIMENTS)),
            'scope':classification_scores([g['scope_status'] for g in gold],
                [p['analysis']['scope_status'] if ok else '__failed__' for p,ok in zip(aligned,valid)],sorted(contract.SCOPES)),
            'issues':{'micro_precision':precision,'micro_recall':recall,
                'micro_f1':2*precision*recall/(precision+recall) if precision+recall else 0.0,
                'macro_f1':sum(r['f1'] for r in issue_rows)/len(issue_rows),
                'exact_match_rate':sum(ok and a==b for a,b,ok in zip(expected,actual,valid))/len(gold),
                'per_label':issue_rows,'zero_division':0},
            'limitations':['按源标签平衡抽样，不能估计平台真实分布','宏平均保留全部预定义类别，零支持类别 F1 记 0',
                            '失败项保留在总分母；问题微平均按标签计数，须结合契约通过率和完全匹配率解读',
                            '模型 confidence 不是实测准确率','本评估不证明经营效果或因果关系']}
    return result
