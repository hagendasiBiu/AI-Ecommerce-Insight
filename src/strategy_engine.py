"""Phase 4 evidence aggregation and explicitly provisional issue ranking."""
import hashlib
import json
import pandas as pd
from src.review_analysis import contract

BASE_F_WEIGHT = 0.35 / (0.35 + 0.30)


def aggregate_evidence(records, reviews, sample_id='phase4-sample-v1'):
    """Count one review once per issue. No inference of sales, time trends or economic loss."""
    source = {r['review_id']: r for r in reviews}
    if len(source) != len(reviews):
        raise ValueError('Duplicate source IDs')
    seen, accepted, groups = set(), [], {}
    failures = 0
    for record in records:
        rid = record['review_id']
        if rid in seen or rid not in source:
            raise ValueError('Duplicate or unknown result ID')
        seen.add(rid)
        if record['status'] != 'validated':
            failures += 1
            continue
        raw = record['analysis']
        analysis = contract.validate_output({key: raw[key] for key in contract.FIELDS}, source[rid])
        if analysis['scope_status'] != 'in_scope' or analysis['sentiment'] == 'unknown':
            continue
        accepted.append(analysis)
        for issue in analysis['issues']:
            if issue['evidence'] not in source[rid]['review_text'] or not issue['evidence'].strip():
                raise ValueError('Evidence is not present in the source')
            group = groups.setdefault(issue['label'], {})
            group[rid] = {'review_id': rid, 'quote': issue['evidence'], 'sentiment': analysis['sentiment']}
    if len(seen) != len(reviews):
        raise ValueError('Missing results; supply explicit failed items')
    eligible_n = len(accepted)
    max_count = max((len(group) for group in groups.values()), default=0)
    issues, facts = [], {}
    for label in sorted(groups):
        members = list(groups[label].values())
        count = len(members)
        negative = sum(m['sentiment'] == 'negative' for m in members)
        mixed = sum(m['sentiment'] == 'mixed' for m in members)
        f = count / max_count if max_count else 0
        n = negative / count if count else 0
        score = BASE_F_WEIGHT * f + (1 - BASE_F_WEIGHT) * n
        band = '样本不足，先人工核查' if count < 3 else ('优先核查' if score >= .75 else '重点核查' if score >= .5 else '持续跟踪' if score >= .25 else '低优先级')
        fact_ids = [label + '.review_count', label + '.sample_share', label + '.negative_fraction']
        facts.update({fact_ids[0]: {'value': count, 'unit': 'model_flagged_reviews', 'denominator': eligible_n},
                      fact_ids[1]: {'value': count / eligible_n if eligible_n else None, 'unit': 'sample_fraction', 'denominator': eligible_n},
                      fact_ids[2]: {'value': n, 'unit': 'negative_sentiment_fraction_among_issue_reviews', 'denominator': count}})
        issues.append({'issue_label': label, 'review_count': count, 'denominator': eligible_n,
                       'sample_share': count / eligible_n if eligible_n else None,
                       'strict_negative_count': negative, 'mixed_count': mixed,
                       'F': f, 'N': n, 'priority_score': score, 'priority_band': band,
                       'fact_ids': fact_ids, 'evidence': members[:3],
                       'human_review_status': 'pending', 'support_sufficient_for_prototype': count >= 3})
    issues.sort(key=lambda r: (-r['priority_score'], -r['review_count'], r['issue_label']))
    sentiment_counts = {s: sum(a['sentiment'] == s for a in accepted) for s in ['positive', 'neutral', 'negative', 'mixed']}
    body = {'sample_id': sample_id, 'scope': 'exploratory_development_sample_only',
            'requested_reviews': len(reviews), 'validated_in_scope_known_sentiment_reviews': eligible_n,
            'failed_items': failures, 'excluded_scope_or_unknown': len(reviews) - failures - eligible_n,
            'source_type': 'public_corpus_model_extraction_not_platform_business_metrics',
            'sentiment_counts': sentiment_counts, 'issues': issues, 'facts': facts,
            'human_review_status': 'pending',
            'priority_model': {'version': 'available-fn-v1', 'F_weight': BASE_F_WEIGHT,
                               'N_weight': 1 - BASE_F_WEIGHT, 'missing_G': True, 'missing_H': True},
            'limitations': ['20条调试样本不能外推平台', '模型提取尚未人工审核',
                            '无商品/订单/价格/日期/点赞字段', '无经营效果或因果证据',
                            '问题标签为多标签，各问题样本占比之和可以超过100%',
                            '语料来源平台、采集时间和许可尚未确认']}
    if sample_id.startswith('workspace:'):
        body['source_type'] = 'workspace_import_model_extraction_source_unverified'
        body['limitations'][0] = f'{len(reviews)}条分析样本不能外推总体'
        body['limitations'][-1] = '导入数据的来源、采集口径与使用权限需单独核验'
    body['evidence_id'] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return body


def sensitivity_table(evidence):
    """A constant N means unchanged order is algebraic, not external robustness evidence."""
    rows = []
    for weight in [.35, BASE_F_WEIGHT, .70]:
        scores = [(issue['issue_label'], weight * issue['F'] + (1 - weight) * issue['N']) for issue in evidence['issues']]
        for label, score in scores:
            # Competition rank; tied scores share rank, deterministic label sort is not substantive rank.
            rank = 1 + sum(other > score + 1e-12 for _, other in scores)
            rows.append({'F_weight': weight, 'N_weight': 1 - weight, 'issue_label': label,
                         'score': score, 'rank': rank})
    return pd.DataFrame(rows)
