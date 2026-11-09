"""Weak-label agreement and repeat stability must not be presented as human accuracy."""
from pathlib import Path
import tempfile
import unittest
import pandas as pd
from src.ai_annotation import summarize, consistency


class AIStudyTests(unittest.TestCase):
    def item(self,rid,sentiment,status='validated',issues=None):
        return {'review_id':rid,'status':status,'analysis':{'sentiment':sentiment,'scope_status':'in_scope',
            'issues':issues or [],'needs_review':False} if status=='validated' else None}

    def test_weak_labels_are_not_gold_and_failure_stays_in_denominator(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'data/processed').mkdir(parents=True)
            pd.DataFrame([{'review_id':'a','source_label':1},{'review_id':'b','source_label':0}]).to_csv(
                root/'data/processed/split_manifest_private.csv',index=False)
            result=summarize(root,[{'review_id':'a'},{'review_id':'b'}],{'a':self.item('a','positive'),
                'b':self.item('b','negative','validation_failed')},[],1.5)
            self.assertEqual(result['source_label_agreement']['agreement_rate'],.5)
            self.assertEqual(result['contract_pass_rate'],.5)
            self.assertIsNone(result['independent_human_accuracy'])
            self.assertIsNone(result['manual_efficiency_gain'])

    def test_repeated_valid_positive_does_not_imply_model_correctness(self):
        first={'a':self.item('a','positive'),'b':self.item('b','negative')}
        second={'a':self.item('a','positive'),'b':self.item('b','unknown','validation_failed')}
        result=consistency(first,second)
        self.assertEqual(result['sentiment_exact_agreement'],.5)
        self.assertEqual(result['valid_pairs'],1)
        self.assertIn('不是准确率',result['interpretation'])

    def test_consistency_requires_same_unique_task_set(self):
        with self.assertRaises(ValueError): consistency({'a':self.item('a','positive')},{})


if __name__=='__main__': unittest.main()
