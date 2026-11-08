"""Synthetic unit fixtures test denominators and draft review gates, not business outcomes."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from src.strategy_engine import aggregate_evidence, sensitivity_table
from src.review_store import ReviewStore

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('diagnosis_node', ROOT / 'dify/nodes/validate_diagnosis.py')
diagnosis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnosis)


def fixtures():
    reviews = [{'review_id': str(i), 'review_text': '掉色，裤子太长', 'language': 'zh', 'product_category': 'clothing'} for i in range(3)]
    records = []
    for review in reviews:
        records.append({'review_id': review['review_id'], 'status': 'validated', 'analysis': {
            'review_id': review['review_id'], 'scope_status': 'in_scope', 'sentiment': 'negative',
            'sentiment_evidence': ['掉色'], 'issues': [{'label': 'product_quality.color_fading', 'evidence': '掉色'},
                                                     {'label': 'size_spec.length_mismatch', 'evidence': '裤子太长'}],
            'user_need': '', 'issue_summary': '', 'confidence': .9, 'needs_review': False}})
    return records, reviews


def diagnosis_fixture(evidence):
    issue = evidence['issues'][0]
    return {'evidence_id': evidence['evidence_id'], 'findings': [{
        'finding_id': 'D1', 'issue_label': issue['issue_label'], 'fact_ids': issue['fact_ids'],
        'evidence_review_ids': [issue['evidence'][0]['review_id']],
        'possible_causes': [{'hypothesis': '可能存在需要核查的商品体验问题', 'status': 'unverified'}],
        'next_validation': '人工查看评论并核对实际商品'}], 'limitations': ['样本小且未人工审核']}


class PriorityTests(unittest.TestCase):
    def test_multi_label_denominator_not_exploded(self):
        evidence = aggregate_evidence(*fixtures())
        self.assertEqual(evidence['validated_in_scope_known_sentiment_reviews'], 3)
        self.assertEqual([i['review_count'] for i in evidence['issues']], [3, 3])
        self.assertEqual(sum(i['sample_share'] for i in evidence['issues']), 2)

    def test_unknown_excluded_and_failure_explicit(self):
        records, reviews = fixtures()
        records[0]['analysis'].update(sentiment='unknown', issues=[], sentiment_evidence=[])
        records[1] = {'review_id': '1', 'status': 'workflow_item_failed', 'analysis': None}
        evidence = aggregate_evidence(records, reviews)
        self.assertEqual(evidence['validated_in_scope_known_sentiment_reviews'], 1)
        self.assertEqual(evidence['failed_items'], 1)
        self.assertEqual(evidence['excluded_scope_or_unknown'], 1)

    def test_mixed_not_counted_as_strict_negative(self):
        records, reviews = fixtures()
        records[0]['analysis']['sentiment'] = 'mixed'
        issue = aggregate_evidence(records, reviews)['issues'][0]
        self.assertEqual(issue['strict_negative_count'], 2)
        self.assertEqual(issue['mixed_count'], 1)
        self.assertAlmostEqual(issue['N'], 2/3)

    def test_duplicate_or_missing_results_rejected(self):
        records, reviews = fixtures()
        with self.assertRaises(ValueError):
            aggregate_evidence(records + records[:1], reviews)
        with self.assertRaises(ValueError):
            aggregate_evidence(records[:1], reviews)

    def test_small_support_overrides_priority_band(self):
        records, reviews = fixtures()
        evidence = aggregate_evidence(records[:1], reviews[:1])
        self.assertEqual(evidence['issues'][0]['priority_band'], '样本不足，先人工核查')

    def test_absent_issues_no_division_by_zero(self):
        records, reviews = fixtures()
        for r in records:
            r['analysis'].update(sentiment='positive', issues=[])
        self.assertEqual(aggregate_evidence(records, reviews)['issues'], [])

    def test_weights_and_tied_ranks(self):
        evidence = aggregate_evidence(*fixtures())
        table = sensitivity_table(evidence)
        self.assertTrue(table['rank'].eq(1).all())
        self.assertTrue(table['score'].between(0, 1).all())
        self.assertAlmostEqual(evidence['priority_model']['F_weight'], 7/13)

    def test_out_of_source_quote_rejected(self):
        records, reviews = fixtures()
        records[0]['analysis']['issues'][0]['evidence'] = '编造证据'
        with self.assertRaises(ValueError):
            aggregate_evidence(records, reviews)


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.evidence = aggregate_evidence(*fixtures())
        self.value = diagnosis_fixture(self.evidence)

    def test_valid_references_still_pending(self):
        result = diagnosis.validate_diagnosis(self.value, self.evidence)
        self.assertEqual(result['human_review_status'], 'pending')

    def test_forged_fact_rejected(self):
        self.value['findings'][0]['fact_ids'] = ['gmv_growth']
        with self.assertRaises(ValueError):
            diagnosis.validate_diagnosis(self.value, self.evidence)

    def test_wrong_issue_fact_rejected(self):
        self.value['findings'][0]['fact_ids'] = self.evidence['issues'][1]['fact_ids']
        with self.assertRaises(ValueError):
            diagnosis.validate_diagnosis(self.value, self.evidence)

    def test_forged_quote_id_rejected(self):
        self.value['findings'][0]['evidence_review_ids'] = ['not-in-evidence']
        with self.assertRaises(ValueError):
            diagnosis.validate_diagnosis(self.value, self.evidence)

    def test_cause_must_be_hypothesis(self):
        self.value['findings'][0]['possible_causes'][0]['status'] = 'proven'
        with self.assertRaises(ValueError):
            diagnosis.validate_diagnosis(self.value, self.evidence)

    def test_invented_numeric_claim_rejected(self):
        self.value['findings'][0]['next_validation'] = '已经提升50%'
        with self.assertRaises(ValueError):
            diagnosis.validate_diagnosis(self.value, self.evidence)

    def test_malformed_json_reports_failure(self):
        result = json.loads(diagnosis.main('not-json', json.dumps(self.evidence))['result'])
        self.assertEqual(result['status'], 'validation_failed')


class ReviewGateTests(unittest.TestCase):
    def test_unapproved_not_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ReviewStore(Path(folder) / 'reviews.sqlite')
            store.save_draft({'action': 'synthetic-test-draft'})
            self.assertEqual(store.approved(), [])

    def test_explicit_approval_and_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ReviewStore(Path(folder) / 'reviews.sqlite')
            draft = store.save_draft({'action': 'synthetic-test-draft'})
            store.decide(draft, 'approved', 'unit-test-reviewer-not-human-evidence', 'fixture decision')
            self.assertEqual(len(store.approved()), 1)
            store.decide(draft, 'rejected', 'unit-test-reviewer', 'fixture rejection')
            self.assertEqual(store.approved(), [])

    def test_modified_content_requires_new_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ReviewStore(Path(folder) / 'reviews.sqlite')
            old = store.save_draft({'action': 'old test draft'})
            store.decide(old, 'approved', 'test reviewer', 'fixture decision')
            new = store.save_draft({'action': 'modified test draft'}, supersedes=old)
            self.assertNotEqual(old, new)
            self.assertEqual(store.approved(), [])
            with self.assertRaises(ValueError):
                store.decide(old, 'approved', 'test reviewer', 'cannot reapprove obsolete content')


if __name__ == '__main__':
    unittest.main()
