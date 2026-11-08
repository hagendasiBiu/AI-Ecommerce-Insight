"""Synthetic contract fixtures only, not real model outputs or measured accuracy."""
import importlib.util
from pathlib import Path
import json
import unittest
from src.review_analysis import contract, validate_batch_response

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('parse_reviews_node', ROOT / 'dify/nodes/parse_reviews.py')
batch_node = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch_node)


def review(text='裤子太长，面料扎人。'):
    return {'review_id': 'unit-fixture-1', 'review_text': text, 'language': 'zh', 'product_category': 'clothing'}


def output():
    return {'review_id': 'unit-fixture-1', 'scope_status': 'in_scope', 'sentiment': 'negative',
            'sentiment_evidence': ['裤子太长'],
            'issues': [{'label': 'size_spec.length_mismatch', 'evidence': '裤子太长'},
                       {'label': 'product_quality.material_quality', 'evidence': '面料扎人'}],
            'user_need': '', 'issue_summary': '裤长过长且面料扎人', 'confidence': 0.9, 'needs_review': False}


class ContractTests(unittest.TestCase):
    def test_multi_label_and_unreviewed(self):
        result = contract.validate_output(output(), review())
        self.assertEqual(result['primary_category'], ['product_quality', 'size_spec'])
        self.assertEqual(result['human_review_status'], 'pending')

    def test_unknown_can_have_no_evidence(self):
        value = output()
        value.update(sentiment='unknown', sentiment_evidence=[], issues=[], confidence=0.2)
        self.assertTrue(contract.validate_output(value, review('还没拆包'))['needs_review'])

    def test_invented_evidence_rejected(self):
        value = output()
        value['issues'][0]['evidence'] = '已经退款100元'
        with self.assertRaisesRegex(ValueError, 'not_in_source'):
            contract.validate_output(value, review())

    def test_low_confidence_review_forced(self):
        value = output()
        value['confidence'] = 0.79
        self.assertTrue(contract.validate_output(value, review())['needs_review'])

    def test_nonfinite_and_boolean_confidence_rejected(self):
        for confidence in [float('nan'), float('inf'), True, -0.1, 1.1, '0.9']:
            value = output()
            value['confidence'] = confidence
            with self.assertRaises(ValueError):
                contract.validate_output(value, review())

    def test_false_as_string_rejected(self):
        value = output()
        value['needs_review'] = 'false'
        with self.assertRaises(ValueError):
            contract.validate_output(value, review())

    def test_unknown_label_rejected(self):
        value = output()
        value['issues'][0]['label'] = 'delivery.made_up_label'
        with self.assertRaises(ValueError):
            contract.validate_output(value, review())

    def test_duplicate_label_rejected(self):
        value = output()
        value['issues'].append(value['issues'][0].copy())
        with self.assertRaises(ValueError):
            contract.validate_output(value, review())

    def test_positive_cannot_have_complaint_labels(self):
        value = output()
        value['sentiment'] = 'positive'
        with self.assertRaises(ValueError):
            contract.validate_output(value, review())

    def test_input_source_label_forbidden(self):
        value = review()
        value['source_label'] = 0
        with self.assertRaises(ValueError):
            contract.validate_input(value)

    def test_malformed_model_output_explicitly_fails(self):
        for model_text in ['', 'not json', '```json\n{}\n```', '{}']:
            result = json.loads(contract.main(model_text, json.dumps(review()))['result'])
            self.assertEqual(result['status'], 'validation_failed')
            self.assertIsNone(result['analysis'])

    def test_sentiment_needs_original_quote(self):
        value = output()
        value['sentiment_evidence'] = []
        with self.assertRaises(ValueError):
            contract.validate_output(value, review())

    def test_batch_input_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            batch_node.main(json.dumps([review(), review()]))

    def test_batch_input_empty_and_large_rejected(self):
        for items in [[], [review()] * 6]:
            with self.assertRaises(ValueError):
                batch_node.main(json.dumps(items))

    def test_null_iteration_result_counted_as_failure(self):
        result = validate_batch_response({'results': [None]}, [review()])
        self.assertEqual(result[0]['status'], 'workflow_item_failed')

    def test_silently_dropped_iteration_rejected(self):
        with self.assertRaises(ValueError):
            validate_batch_response({'results': []}, [review()])

    def test_swapped_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_batch_response({'results': [{'review_id': 'wrong-id'}]}, [review()])

    def test_code_node_roundtrip(self):
        envelope = contract.main(json.dumps(output()), json.dumps(review()))['result']
        checked = validate_batch_response({'results': [envelope]}, [review()])
        self.assertEqual(checked[0]['status'], 'validated')


if __name__ == '__main__':
    unittest.main()
