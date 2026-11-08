"""Regression tests use a temporary synthetic store, never real human annotations."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.evaluation import AnnotationStore

ROOT=Path(__file__).resolve().parents[1]


class AnnotationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'data/sample').mkdir(parents=True)
        pd.DataFrame([{'review_id':f'fixture-{i}','review_text':'合成测试衣服不错'} for i in range(1,4)]).to_csv(
            self.root/'data/sample/annotation_prompt_dev.csv',index=False)
        self.store=AnnotationStore(self.root)
        self.body=dict(scope_status='in_scope',sentiment='positive',issue_labels=[],evidence=[],
            annotator_id='synthetic-annotator',user_need='',notes='unit fixture',annotation_seconds=4.0)
        for i in [1,2]: self.store.save('prompt_dev',f'fixture-{i}',self.body)

    def tearDown(self): self.temp.cleanup()

    def start(self):
        # A small wrapper also makes this regression runnable in the public code
        # distribution, where real annotation task CSVs are intentionally absent.
        wrapper=self.root/'run_page.py'
        wrapper.write_text('import sys\nfrom pathlib import Path\nimport streamlit as st\n'
            f'sys.path.insert(0,{str(ROOT)!r})\n'
            'real_is_file=Path.exists\n'
            'from unittest.mock import patch\n'
            f'with patch.object(Path,"exists",lambda p: True if str(p).endswith(("annotation_prompt_dev.csv","annotation_heldout_test.csv")) else real_is_file(p)):\n'
            f'    exec(compile(Path({str(ROOT/"app/pages/07_evaluation.py")!r}).read_text(encoding="utf-8"),{str(ROOT/"app/pages/07_evaluation.py")!r},"exec"),dict(__file__={str(ROOT/"app/pages/07_evaluation.py")!r}))\n',encoding='utf-8')
        return AppTest.from_file(str(wrapper),default_timeout=20).run()

    def picker(self,at): return next(s for s in at.selectbox if s.label=='评论编号')

    def test_approval_keeps_selected_review_and_only_updates_that_record(self):
        with patch('src.evaluation.AnnotationStore',return_value=self.store):
            at=self.start()
            self.picker(at).select('fixture-2').run()
            next(t for t in at.text_input if t.label=='真实复核者代号').set_value('synthetic-reviewer')
            at.checkbox[0].check()
            next(b for b in at.button if b.label=='确认人工复核通过').click().run()
            self.assertFalse(list(at.exception))
            self.assertEqual(self.picker(at).value,'fixture-2')
            self.assertTrue(any('已人工复核' in c.value for c in at.caption))
            self.assertEqual(self.store.records('prompt_dev')['fixture-2']['review_status'],'approved')
            self.assertEqual(self.store.records('prompt_dev')['fixture-1']['review_status'],'pending')
            at.run()
            self.assertEqual(self.picker(at).value,'fixture-2')
            next(b for b in at.button if b.label=='下一条未复核').click().run()
            self.assertEqual(self.picker(at).value,'fixture-3')

    def test_first_save_keeps_third_review_selected(self):
        with patch('src.evaluation.AnnotationStore',return_value=self.store):
            at=self.start(); self.picker(at).select('fixture-3').run()
            next(b for b in at.button if b.label=='开始 / 继续计时').click().run()
            next(t for t in at.text_input if t.label=='真实标注者代号').set_value('synthetic-annotator')
            next(s for s in at.selectbox if s.label=='业务范围').select('in_scope')
            next(s for s in at.selectbox if s.label=='情感').select('positive')
            next(b for b in at.button if b.label=='保存人工标注').click().run()
            self.assertFalse(list(at.exception))
            self.assertEqual(self.picker(at).value,'fixture-3')
            self.assertEqual(self.store.records('prompt_dev')['fixture-3']['review_status'],'pending')


if __name__=='__main__': unittest.main()
