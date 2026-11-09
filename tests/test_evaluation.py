"""Synthetic fixtures only; no human gold or heldout text is read here."""
import json
from pathlib import Path
import tempfile
import unittest
import pandas as pd
from src.evaluation import AnnotationStore, evaluate, classification_scores


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        (self.root/'data/sample').mkdir(parents=True)
        for split in ['prompt_dev','heldout_test']:
            pd.DataFrame([{'review_id':str(i),'review_text':'衣服掉色。'} for i in range(100 if split=='heldout_test' else 2)]).to_csv(
                self.root/f'data/sample/annotation_{split}.csv',index=False)
        for p in ['docs/annotation_guide.md','dify/review_analysis_workflow.yml','dify/nodes/validate_review.py']:
            path=self.root/p; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('synthetic')
        self.store=AnnotationStore(self.root)
        self.body=dict(scope_status='in_scope',sentiment='negative',issue_labels=['product_quality.color_fading'],
            evidence=[{'label':'product_quality.color_fading','quote':'掉色'}],annotator_id='human-fixture',
            user_need='',notes='',annotation_seconds=3.5)

    def tearDown(self): self.temp.cleanup()

    def test_no_auto_gold_and_split_isolation(self):
        self.assertEqual(self.store.progress('heldout_test')['completed'],0)
        self.store.save('prompt_dev','0',self.body)
        self.assertEqual(self.store.progress('prompt_dev')['completed'],1)
        self.assertEqual(self.store.progress('heldout_test')['completed'],0)

    def test_evidence_must_match_original_and_label(self):
        for bad in [[],[{'label':'product_quality.color_fading','quote':'不存在'}],
                    [{'label':'delivery.delay','quote':'掉色'}]]:
            with self.assertRaises(ValueError): self.store.save('prompt_dev','0',{**self.body,'evidence':bad})

    def test_requires_actor_time_and_known_member(self):
        for change in [{'annotator_id':''},{'annotation_seconds':0},{'annotation_seconds':float('nan')},
                       {'sentiment':''},{'issue_labels':['unknown']},{'sentiment':'positive'}]:
            with self.assertRaises(ValueError): self.store.save('prompt_dev','0',{**self.body,**change})
        with self.assertRaises(ValueError): self.store.save('prompt_dev','not-in-split',self.body)

    def test_edit_invalidates_review(self):
        self.store.save('prompt_dev','0',self.body); self.store.approve('prompt_dev','0','same-human')
        self.assertEqual(self.store.records('prompt_dev')['0']['review_status'],'approved')
        self.store.save('prompt_dev','0',{**self.body,'notes':'修订'})
        self.assertEqual(self.store.records('prompt_dev')['0']['review_status'],'pending')

    def test_ai_exposed_holdout_cannot_be_frozen_as_independent_human_gold(self):
        study=self.root/'data/processed/ai_annotation_study.json'
        study.write_text(json.dumps({'user_authorized_ai_only':True}),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'已进入 AI 研究'):
            self.store.freeze('human')

    def test_freeze_requires_all_reviewed_and_prevents_edits(self):
        with self.assertRaises(ValueError): self.store.freeze('human')
        for i in range(100):
            self.store.save('heldout_test',str(i),self.body)
            self.store.approve('heldout_test',str(i),'human')
        frozen=self.store.freeze('human'); self.assertEqual(frozen['count'],100)
        self.assertEqual(frozen,self.store.freeze('human'))
        with self.assertRaises(ValueError): self.store.save('heldout_test','0',self.body)
        with self.assertRaises(ValueError): self.store.approve('heldout_test','0','human')


class MetricsTests(unittest.TestCase):
    def fixture(self):
        gold=[dict(review_id='a',sentiment='positive',scope_status='in_scope',issue_labels=[],review_status='approved'),
              dict(review_id='b',sentiment='negative',scope_status='in_scope',issue_labels=['delivery.delay'],review_status='approved')]
        pred=[dict(review_id='a',status='validated',analysis=dict(sentiment='positive',scope_status='in_scope',issues=[])),
              dict(review_id='b',status='validated',analysis=dict(sentiment='positive',scope_status='in_scope',issues=[]))]
        return gold,pred

    def test_fixed_macro_denominator(self):
        r=classification_scores(['positive','negative'],['positive','positive'],['positive','negative','unknown'])
        self.assertAlmostEqual(r['macro_f1'],(2/3)/3)
        self.assertEqual(r['per_class'][2]['support'],0)

    def test_missing_duplicate_or_unreviewed_rejected(self):
        g,p=self.fixture()
        for bad in [p[:1],p+[p[0]]]:
            with self.assertRaises(ValueError): evaluate(g,bad)
        g[0]['review_status']='pending'
        with self.assertRaises(ValueError): evaluate(g,p)

    def test_failed_empty_gold_not_scored_as_correct(self):
        g,p=self.fixture(); p[0]={'review_id':'a','status':'workflow_item_failed','analysis':None}
        result=evaluate(g,p)
        self.assertEqual(result['contract_pass_rate'],.5)
        self.assertEqual(result['sentiment']['accuracy'],0)
        self.assertEqual(result['issues']['exact_match_rate'],0)
        self.assertEqual(result['n'],2)

    def test_alignment_by_id_and_multilabel_counts(self):
        g,p=self.fixture(); p[1]['analysis'].update(sentiment='negative',issues=[{'label':'delivery.delay','evidence':'慢'}])
        result=evaluate(g,list(reversed(p)))
        self.assertEqual(result['issues']['micro_f1'],1)
        self.assertEqual(result['issues']['exact_match_rate'],1)
        self.assertEqual(result['sentiment']['accuracy'],1)


if __name__=='__main__': unittest.main()
