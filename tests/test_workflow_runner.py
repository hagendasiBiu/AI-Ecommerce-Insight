"""Credential changes must not reuse another Dify app's cached response."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from src.workflow_runner import run_recorded,load_env


class WorkflowCacheTests(unittest.TestCase):
    def test_same_key_reuses_and_changed_key_calls_new_app(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ,{'DIFY_API_BASE_URL':'https://example.invalid/v1','DIFY_API_KEY':'synthetic-a'}):
                with patch('src.workflow_runner.DifyClient') as client:
                    client.return_value.run_inputs.return_value={'status':'succeeded','outputs':{},'total_tokens':1}
                    self.assertFalse(run_recorded(root,{'input':'x'},'DIFY_API_KEY','v1','test')[1])
                    self.assertTrue(run_recorded(root,{'input':'x'},'DIFY_API_KEY','v1','test')[1])
                    os.environ['DIFY_API_KEY']='synthetic-b'
                    self.assertFalse(run_recorded(root,{'input':'x'},'DIFY_API_KEY','v1','test')[1])
                    self.assertEqual(client.return_value.run_inputs.call_count,2)

    def test_unknown_attempt_not_automatically_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{'DIFY_API_BASE_URL':'https://example.invalid/v1','DIFY_API_KEY':'synthetic-a'}):
                with patch('src.workflow_runner.DifyClient') as client:
                    client.return_value.run_inputs.side_effect=TimeoutError()
                    for _ in range(2):
                        with self.assertRaises(RuntimeError):
                            run_recorded(Path(directory),{'input':'x'},'DIFY_API_KEY','v1','test')
                    self.assertEqual(client.return_value.run_inputs.call_count,1)

    def test_local_config_correction_reloads_in_long_running_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'.env'
            with patch.dict(os.environ,{},clear=False):
                path.write_text('DIFY_API_KEY=synthetic-a\n',encoding='utf-8'); load_env(root)
                path.write_text('DIFY_API_KEY=synthetic-b\n',encoding='utf-8'); load_env(root)
                self.assertEqual(os.environ['DIFY_API_KEY'],'synthetic-b')


if __name__=='__main__': unittest.main()
