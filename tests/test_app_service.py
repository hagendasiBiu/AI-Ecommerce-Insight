"""Temporary workspaces and synthetic fixtures only; no paid calls or real approvals."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from src.app_service import AppService, parse_upload
from src.data_processing import digest, fingerprint, normalize_text


class UploadTests(unittest.TestCase):
    def test_blank_and_missing_column(self):
        for content in [b'',b'wrong\ntext',b'review_text\n"   "']:
            with self.assertRaises(ValueError): parse_upload(content)

    def test_dedupe_mask_and_ignore_source_label(self):
        content='cat,label,review\n衣服,0,裤子质量好\n衣服,1,裤子质量好！\n衣服,0,联系13812345678\n手机,1,不应纳入'.encode()
        reviews,meta=parse_upload(content)
        self.assertEqual(len(reviews),2)
        self.assertEqual(meta['duplicates_removed'],1)
        self.assertTrue(meta['source_labels_ignored'])
        self.assertEqual(set(reviews[0]),{'review_id','review_text','language','product_category'})
        self.assertNotIn('13812345678',reviews[1]['review_text'])

    def test_declared_and_fingerprint_holdout_rejected(self):
        text='保留测试内容'
        protected=digest('clothing:'+fingerprint(normalize_text(text)))
        with self.assertRaises(ValueError): parse_upload(('review_text\n'+text).encode(),[protected])
        with self.assertRaises(ValueError): parse_upload(b'review_id,review_text\nprotected-id,new text',['protected-id'])

    def test_non_chinese_not_silently_claimed_supported(self):
        with self.assertRaises(ValueError): parse_upload(b'language,review_text\nen,good shirt')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.service=AppService(self.root)
        self.review={'review_id':'r1','review_text':'很好','language':'zh','product_category':'clothing'}
        self.wid=self.service.create('first',[self.review])

    def tearDown(self): self.folder.cleanup()

    def result(self):
        return {'status':'validated','review_id':'r1','analysis':{
            'review_id':'r1','scope_status':'in_scope','sentiment':'positive','sentiment_evidence':['很好'],
            'issues':[],'user_need':'','issue_summary':'','confidence':.9,'needs_review':False}}

    def test_reimport_idempotent_and_state_persists(self):
        self.assertEqual(self.wid,self.service.create('new name',[self.review]))
        other=AppService(self.root)
        self.assertEqual(len(other.reviews(self.wid)),1)

    def test_workspace_isolation(self):
        second=self.service.create('second',[{**self.review,'review_id':'r2'}])
        self.service.save_analyses(self.wid,[self.result()])
        self.assertEqual(self.service.analyses(second),[])
        with self.assertRaises(ValueError): self.service.save_analyses(second,[self.result()])

    def test_no_diagnosis_without_evidence_and_no_empty_call(self):
        with self.assertRaises(ValueError): self.service.call(self.wid,'diagnosis')
        with self.assertRaises(ValueError): self.service.call(self.wid,'review',[])
        with self.assertRaises(ValueError): self.service.call(self.wid,'review',['r1']*2)

    def test_changed_evidence_invalidates_downstream(self):
        self.service.save_analyses(self.wid,[self.result()])
        evidence=self.service.build_evidence(self.wid)
        self.service.put(self.wid,'diagnosis',{'evidence_id':evidence['evidence_id']})
        changed=self.result(); changed['analysis'].update(sentiment='negative')
        self.service.save_analyses(self.wid,[changed])
        self.service.build_evidence(self.wid)
        self.assertIsNone(self.service.get(self.wid,'diagnosis'))

    def test_mocked_api_persists_without_source_labels(self):
        (self.root/'dify').mkdir()
        (self.root/'dify/review_analysis_workflow.yml').write_text('synthetic export fixture')
        response={'status':'succeeded','outputs':{'results':[self.result()]},'total_tokens':0}
        with patch('src.app_service.run_recorded',return_value=(response,False)) as call:
            result=self.service.call(self.wid,'review',['r1'])
        payload=json.loads(call.call_args.args[1]['reviews_json'])
        self.assertEqual(payload,[self.review])
        self.assertEqual(result['validated'],1)
        self.assertEqual(len(self.service.analyses(self.wid)),1)

    def test_review_state_is_evidence_bound(self):
        self.service.save_analyses(self.wid,[self.result()])
        evidence=self.service.build_evidence(self.wid)
        self.service.review_store.save_draft({'evidence_id':'different','strategy':{}})
        self.assertEqual(self.service.drafts(self.wid),[])

    def test_uploaded_sample_count_not_fixed_to_twenty(self):
        self.service.save_analyses(self.wid,[self.result()])
        evidence=self.service.build_evidence(self.wid)
        self.assertIn('1条分析样本',evidence['limitations'][0])

    def test_reordered_identical_analysis_keeps_approval_evidence(self):
        self.service.save_analyses(self.wid,[self.result()])
        evidence=self.service.build_evidence(self.wid)
        self.service.put(self.wid,'diagnosis',{'evidence_id':evidence['evidence_id']})
        self.service.save_analyses(self.wid,[self.result()])
        self.assertEqual(self.service.build_evidence(self.wid)['evidence_id'],evidence['evidence_id'])
        self.assertIsNotNone(self.service.get(self.wid,'diagnosis'))

    def test_pdf_rejects_unapproved_or_stale_content(self):
        from src.report_generator import generate_workspace_report
        self.service.save_analyses(self.wid,[self.result()])
        evidence=self.service.build_evidence(self.wid)
        with self.assertRaises(ValueError):
            generate_workspace_report(self.root,self.wid,evidence,[])
        draft=self.service.review_store.save_draft({'evidence_id':evidence['evidence_id'],'strategy':{'action':'test'}})
        fake_approved=[{'draft_id':draft,'body':{'evidence_id':evidence['evidence_id'],'strategy':{'action':'test'}}}]
        with self.assertRaises(ValueError): generate_workspace_report(self.root,self.wid,evidence,fake_approved)
