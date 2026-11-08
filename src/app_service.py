"""Local UI service: isolated workspaces, explicit paid calls, and evidence-bound review."""
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import sqlite3
import pandas as pd
from src.data_processing import normalize_text, fingerprint, digest, redact_contacts
from src.review_analysis import contract, validate_batch_response
from src.strategy_engine import aggregate_evidence
from src.workflow_runner import run_recorded
from src.review_store import ReviewStore


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def parse_upload(content, protected_ids=()):
    if not content or len(content) > 15_000_000:
        raise ValueError('文件为空或超过 15 MB。')
    try:
        frame = pd.read_csv(io.BytesIO(content), encoding='utf-8-sig', dtype=str, keep_default_na=False)
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        raise ValueError('请上传 UTF-8 编码、带表头的 CSV 文件。') from None
    if not 1 <= len(frame) <= 20000:
        raise ValueError('单文件应包含 1 至 20,000 行。')
    original_n = len(frame)
    text_col = 'review_text' if 'review_text' in frame else 'review' if 'review' in frame else None
    if not text_col:
        raise ValueError('缺少 review_text 列。也支持原始语料的 review、cat 列。')
    if 'cat' in frame:
        frame = frame.loc[frame['cat'].eq('衣服')]
    if 'product_category' in frame:
        frame = frame.loc[frame['product_category'].isin(['clothing', '衣服', '服饰'])]
    reviews, seen, blank, duplicates = [], set(), 0, 0
    protected = set(protected_ids)
    for _, row in frame.iterrows():
        text = normalize_text(row[text_col])
        fp = fingerprint(text)
        if not fp:
            blank += 1
            continue
        if len(text) > 4000:
            raise ValueError('评论超过 4,000 字符，请先拆分或修正。')
        canonical_id = digest('clothing:' + fp)
        declared_id = row.get('review_id', '')
        if canonical_id in protected or declared_id in protected:
            raise ValueError('上传包含项目保留的独立测试评论，不能进入开发工作区。')
        if fp in seen:
            duplicates += 1
            continue
        seen.add(fp)
        language = row.get('language', '') or 'zh'
        # First product release was validated only with Chinese clothing comments.
        if language != 'zh':
            raise ValueError('当前产品仅开放已验证的中文服饰场景，language 请使用 zh。')
        reviews.append({'review_id': canonical_id, 'review_text': redact_contacts(text),
                        'language': 'zh', 'product_category': 'clothing'})
    if not reviews:
        raise ValueError('没有可用的服饰评论。请检查品类、空白和字段。')
    return reviews, {'uploaded_rows': original_n, 'category_rows': len(frame), 'retained': len(reviews),
                     'blank_rows': blank, 'duplicates_removed': duplicates,
                     'source_labels_ignored': 'label' in frame.columns}


class AppService:
    def __init__(self, root, db_path=None):
        self.root = Path(root)
        self.db_path = Path(db_path) if db_path else self.root / 'data/processed/app_state.sqlite'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT, created_at TEXT, metadata TEXT);
                CREATE TABLE IF NOT EXISTS reviews (workspace TEXT, review_id TEXT, body TEXT, PRIMARY KEY(workspace,review_id));
                CREATE TABLE IF NOT EXISTS analyses (workspace TEXT, review_id TEXT, body TEXT, PRIMARY KEY(workspace,review_id));
                CREATE TABLE IF NOT EXISTS artifacts (workspace TEXT, kind TEXT, body TEXT, PRIMARY KEY(workspace,kind));
            ''')
        self.review_store = ReviewStore(self.root / 'data/processed/strategy_reviews.sqlite')

    def put(self, workspace, kind, value):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute('INSERT OR REPLACE INTO artifacts VALUES (?,?,?)', (workspace, kind, json.dumps(value, ensure_ascii=False, allow_nan=False)))

    def get(self, workspace, kind):
        with closing(sqlite3.connect(self.db_path)) as db:
            row = db.execute('SELECT body FROM artifacts WHERE workspace=? AND kind=?', (workspace, kind)).fetchone()
        return json.loads(row[0]) if row else None

    def create(self, name, reviews, metadata=None):
        for review in reviews:
            contract.validate_input(review)
        if len({r['review_id'] for r in reviews}) != len(reviews):
            raise ValueError('评论 ID 重复。')
        wid = digest(json.dumps(reviews, sort_keys=True, ensure_ascii=False))[:24]
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute('INSERT OR IGNORE INTO workspaces VALUES (?,?,?,?)',
                       (wid, name[:100], datetime.now(timezone.utc).isoformat(), json.dumps(metadata or {}, ensure_ascii=False)))
            db.executemany('INSERT OR IGNORE INTO reviews VALUES (?,?,?)',
                           [(wid, r['review_id'], json.dumps(r, ensure_ascii=False)) for r in reviews])
        return wid

    def workspaces(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            return [dict(zip(['id','name','created_at'], r)) for r in db.execute('SELECT id,name,created_at FROM workspaces ORDER BY created_at DESC')]

    def reviews(self, wid):
        with closing(sqlite3.connect(self.db_path)) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM reviews WHERE workspace=? ORDER BY rowid', (wid,))]

    def analyses(self, wid):
        with closing(sqlite3.connect(self.db_path)) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM analyses WHERE workspace=? ORDER BY review_id', (wid,))]

    def save_analyses(self, wid, results):
        allowed = {r['review_id'] for r in self.reviews(wid)}
        if any(r['review_id'] not in allowed for r in results):
            raise ValueError('分析结果不属于当前工作区。')
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.executemany('INSERT OR REPLACE INTO analyses VALUES (?,?,?)',
                           [(wid, r['review_id'], json.dumps(r, ensure_ascii=False)) for r in results])

    def seed(self):
        if not (self.root / 'data/sample/phase4_review_sample.json').exists():
            # Public code distribution has no unlicensed source comments or private approvals.
            return self.create('空白工作区 · 请上传有权使用的服饰评论', [], {'kind':'empty_public_workspace'})
        reviews = read_json(self.root / 'data/sample/phase4_review_sample.json')
        wid = self.create('已验证案例 · 20 条服饰评论', reviews, {'kind': 'phase4_case_study'})
        if not self.get(wid, 'seeded'):
            self.save_analyses(wid, read_json(self.root / 'data/processed/phase4_review_results.json')['results'])
            self.put(wid, 'evidence', read_json(self.root / 'data/processed/phase4_business_evidence.json'))
            self.put(wid, 'diagnosis', read_json(self.root / 'data/processed/phase4_diagnosis_result.json')['diagnosis'])
            self.put(wid, 'strategy', read_json(self.root / 'data/processed/phase4_strategy_result.json')['strategy_plan'])
            self.put(wid, 'seeded', True)
            self.put(wid, 'analysis_signature', self.analysis_signature(wid))
        elif self.get(wid,'analysis_signature') is None:
            self.put(wid,'analysis_signature',self.analysis_signature(wid))
        return wid

    def analysis_signature(self,wid):
        return digest(json.dumps(sorted(self.analyses(wid),key=lambda r:r['review_id']),sort_keys=True,ensure_ascii=False))

    def build_evidence(self, wid):
        results = self.analyses(wid)
        if not results:
            raise ValueError('请先分析评论。')
        previous = self.get(wid, 'evidence')
        signature = self.analysis_signature(wid)
        if previous and self.get(wid,'analysis_signature') == signature:
            return previous
        ids = {r['review_id'] for r in results}
        reviews = [r for r in self.reviews(wid) if r['review_id'] in ids]
        result = aggregate_evidence(results, reviews, sample_id='workspace:' + wid)
        self.put(wid, 'evidence', result)
        self.put(wid, 'analysis_signature', signature)
        self.put(wid, 'diagnosis', None)
        self.put(wid, 'strategy', None)
        return result

    def call(self, wid, kind, selected_ids=None):
        evidence = self.get(wid, 'evidence')
        if kind == 'review':
            if not selected_ids or not 1 <= len(selected_ids) <= 5 or len(set(selected_ids)) != len(selected_ids):
                raise ValueError('每次请选择 1 至 5 条不同评论。')
            source = {r['review_id']: r for r in self.reviews(wid)}
            if any(rid not in source for rid in selected_ids):
                raise ValueError('选中的评论不属于当前工作区。')
            reviews = [source[rid] for rid in selected_ids]
            inputs, key, file = {'reviews_json': json.dumps(reviews, ensure_ascii=False)}, 'DIFY_API_KEY', 'review_analysis_workflow.yml'
        else:
            if not evidence or not evidence['issues']:
                raise ValueError('请先生成有问题证据的统计。')
            if kind == 'diagnosis':
                inputs, key, file = {'metrics_json': json.dumps(evidence, ensure_ascii=False)}, 'DIFY_DIAGNOSIS_API_KEY', 'business_diagnosis_workflow.yml'
            elif kind == 'strategy':
                diagnosis = self.get(wid, 'diagnosis')
                if not diagnosis or diagnosis['evidence_id'] != evidence['evidence_id']:
                    raise ValueError('请先生成匹配当前证据的诊断。')
                bundle = {'evidence': evidence, 'diagnosis': diagnosis}
                inputs, key, file = {'strategy_json': json.dumps(bundle, ensure_ascii=False)}, 'DIFY_STRATEGY_API_KEY', 'strategy_generation_workflow.yml'
            else:
                raise ValueError('未知操作。')
        version = hashlib.sha256((self.root / 'dify' / file).read_bytes()).hexdigest()
        response, reused = run_recorded(self.root, inputs, key, version, 'app_' + kind)
        self.put(wid, 'last_run', {k: response.get(k) for k in ['workflow_run_id','total_tokens','client_elapsed_seconds','status']})
        if response.get('status') != 'succeeded':
            raise ValueError('平台执行失败，已保存响应。请核对 Dify 日志，勿连续重复提交。')
        if kind == 'review':
            results = validate_batch_response(response['outputs'], reviews)
            self.save_analyses(wid, results)
            self.build_evidence(wid)
            return {'reused': reused, 'items': len(results), 'validated': sum(r['status']=='validated' for r in results)}
        filename = 'validate_diagnosis.py' if kind == 'diagnosis' else 'validate_strategy.py'
        spec = importlib.util.spec_from_file_location('app_' + kind + '_contract', self.root / 'dify/nodes' / filename)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        output_key, value_key = ('diagnosis_json','diagnosis') if kind == 'diagnosis' else ('strategy_result_json','strategy_plan')
        envelope = json.loads(response['outputs'][output_key])
        if envelope.get('status') != 'validated':
            raise ValueError('模型输出未通过校验，已保留原始运行响应。')
        raw = envelope[value_key]
        if kind == 'diagnosis':
            checked = module.validate_diagnosis({k: raw[k] for k in ['evidence_id','findings','limitations']}, evidence)
            self.put(wid, 'strategy', None)
        else:
            checked = module.validate_strategy({k: raw[k] for k in ['evidence_id','strategies']}, bundle)
            for strategy in checked['strategies']:
                self.review_store.save_draft({'evidence_id': evidence['evidence_id'], 'strategy': strategy})
        self.put(wid, kind, checked)
        return {'reused': reused, 'status': 'validated'}

    def drafts(self, wid):
        evidence = self.get(wid, 'evidence')
        if not evidence:
            return []
        with closing(sqlite3.connect(self.review_store.path)) as db:
            records = db.execute('SELECT draft_id,body,status FROM strategy_drafts ORDER BY rowid DESC').fetchall()
        return [{'draft_id': rid, 'body': json.loads(body), 'status': status}
                for rid, body, status in records if json.loads(body).get('evidence_id') == evidence['evidence_id']]
