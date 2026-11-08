"""Mocked transport failures verify code behavior, never assert live Dify integration."""
import io
import json
import unittest
from urllib import error
from src.dify_client import DifyClient, DifyError, AmbiguousRunError

REVIEW = {'review_id': 'transport-fixture', 'review_text': '尺寸偏小', 'language': 'zh', 'product_category': 'clothing'}


def response():
    return io.BytesIO(json.dumps({'workflow_run_id': 'fixture-run-not-real', 'data': {
        'status': 'succeeded', 'outputs': {'results': [None]}, 'total_tokens': 12}}).encode())


class ApiTests(unittest.TestCase):
    def test_request_has_correct_payload_and_authorization(self):
        calls = []
        def transport(req, timeout):
            calls.append((req, timeout))
            return response()
        result = DifyClient('https://api.dify.ai/v1', 'test-key-not-real', opener=transport).run_reviews([REVIEW])
        self.assertEqual(result['http_attempts'], 1)
        req = calls[0][0]
        self.assertEqual(req.full_url, 'https://api.dify.ai/v1/workflows/run')
        self.assertEqual(req.get_header('Authorization'), 'Bearer test-key-not-real')
        payload = json.loads(req.data)
        self.assertEqual(payload['response_mode'], 'blocking')
        self.assertEqual(json.loads(payload['inputs']['reviews_json']), [REVIEW])

    def test_429_bounded_retry(self):
        calls, sleeps = [], []
        def transport(req, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise error.HTTPError(req.full_url, 429, 'fixture', {}, None)
            return response()
        DifyClient('https://api.dify.ai/v1', 'fake', opener=transport, sleeper=sleeps.append).run_reviews([REVIEW])
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [2, 4])

    def test_429_retries_stop(self):
        calls = []
        def transport(req, timeout):
            calls.append(1)
            raise error.HTTPError(req.full_url, 429, 'fixture', {}, None)
        with self.assertRaises(DifyError):
            DifyClient('https://api.dify.ai/v1', 'fake', opener=transport, sleeper=lambda _: None).run_reviews([REVIEW])
        self.assertEqual(len(calls), 3)

    def test_auth_error_not_retried(self):
        calls = []
        def transport(req, timeout):
            calls.append(1)
            raise error.HTTPError(req.full_url, 401, 'secret must not print', {}, None)
        with self.assertRaisesRegex(DifyError, '401'):
            DifyClient('https://api.dify.ai/v1', 'fake', opener=transport).run_reviews([REVIEW])
        self.assertEqual(len(calls), 1)

    def test_timeout_and_500_not_replayed(self):
        for exception in [TimeoutError('fixture'), error.HTTPError('https://api.dify.ai', 500, 'fixture', {}, None)]:
            calls = []
            def transport(req, timeout):
                calls.append(1)
                raise exception
            with self.assertRaises(AmbiguousRunError):
                DifyClient('https://api.dify.ai/v1', 'fake', opener=transport).run_reviews([REVIEW])
            self.assertEqual(len(calls), 1)

    def test_bad_json_marked_ambiguous(self):
        with self.assertRaises(AmbiguousRunError):
            DifyClient('https://api.dify.ai/v1', 'fake', opener=lambda *args, **kw: io.BytesIO(b'bad json')).run_reviews([REVIEW])

    def test_missing_key_and_insecure_url_rejected(self):
        for base, key in [('https://api.dify.ai/v1', ''), ('http://api.dify.ai/v1', 'fake')]:
            with self.assertRaises(ValueError):
                DifyClient(base, key)

    def test_key_not_in_error_message(self):
        def transport(req, timeout):
            raise error.HTTPError(req.full_url, 401, 'test-secret', {}, None)
        with self.assertRaises(DifyError) as caught:
            DifyClient('https://api.dify.ai/v1', 'test-secret', opener=transport).run_reviews([REVIEW])
        self.assertNotIn('test-secret', str(caught.exception))

    def test_non_ascii_placeholder_rejected_before_transport(self):
        with self.assertRaises(ValueError):
            DifyClient('https://api.dify.ai/v1', '这里填密钥')
