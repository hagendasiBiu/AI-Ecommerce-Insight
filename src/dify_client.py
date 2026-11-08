"""Dify Service API client with bounded 429 retry; ambiguous POSTs are never auto-replayed."""
from datetime import datetime, timezone
import json
import time
from urllib import request, error, parse


class DifyError(RuntimeError):
    pass


class AmbiguousRunError(DifyError):
    """The server may have started/billed the run; check Dify logs before resubmission."""


class DifyClient:
    def __init__(self, base_url, api_key, timeout=90, opener=None, sleeper=time.sleep):
        base_url = base_url.rstrip('/')
        url = parse.urlsplit(base_url)
        if url.scheme != 'https' or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use the HTTPS Service API base URL from your Dify app, without query or credentials')
        if not api_key or not api_key.strip():
            raise ValueError('DIFY_API_KEY is missing; set it locally, not in chat')
        if not api_key.isascii() or any(c.isspace() for c in api_key):
            raise ValueError('API key contains non-ASCII characters or whitespace; replace placeholder text locally')
        self.base_url, self.api_key, self.timeout = base_url, api_key.strip(), timeout
        self.opener, self.sleeper = opener or request.urlopen, sleeper

    def run_reviews(self, reviews, user='ecommerce-portfolio-local'):
        from src.review_analysis import contract
        if not isinstance(reviews, list) or not 1 <= len(reviews) <= 5:
            raise ValueError('Pilot batch size must be 1 to 5')
        for review in reviews:
            contract.validate_input(review)
        if len({r['review_id'] for r in reviews}) != len(reviews):
            raise ValueError('Duplicate review IDs in request')
        return self.run_inputs({'reviews_json': json.dumps(reviews, ensure_ascii=False)}, user)

    def run_inputs(self, inputs, user='ecommerce-portfolio-local'):
        """Invoke an explicitly configured real Workflow; statistical aggregation stays local."""
        if not isinstance(inputs, dict) or not inputs or len(json.dumps(inputs, ensure_ascii=False)) > 200000:
            raise ValueError('Workflow inputs must be a nonempty bounded object')
        payload = {'inputs': inputs, 'response_mode': 'blocking', 'user': user}
        req = request.Request(self.base_url + '/workflows/run',
                              data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                              headers={'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json'},
                              method='POST')
        started = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        attempts = 0
        while True:
            attempts += 1
            try:
                # Never forward the bearer key on redirects to another endpoint.
                if self.opener == request.urlopen:
                    class NoRedirect(request.HTTPRedirectHandler):
                        def redirect_request(self, req, fp, code, msg, headers, newurl):
                            return None
                    transport = request.build_opener(NoRedirect()).open
                else:
                    transport = self.opener
                with transport(req, timeout=self.timeout) as response:
                    body = response.read(2_000_001)
                    if len(body) > 2_000_000:
                        raise AmbiguousRunError('Response too large; reconcile using Dify logs')
                try:
                    result = json.loads(body)
                except (ValueError, UnicodeError):
                    raise AmbiguousRunError('Non-JSON response; reconcile using Dify logs') from None
                break
            except error.HTTPError as exc:
                if exc.code == 429 and attempts < 3:
                    self.sleeper(min(2 ** attempts, 5))
                    continue
                if exc.code >= 500:
                    raise AmbiguousRunError(f'Dify HTTP {exc.code}; run may have started, no automatic replay') from None
                raise DifyError(f'Dify HTTP {exc.code}; check credentials, quota, URL and app publishing') from None
            except (error.URLError, TimeoutError, OSError):
                raise AmbiguousRunError('Connection failed/timed out; inspect Dify logs before retrying') from None
        if not isinstance(result, dict) or not isinstance(result.get('data'), dict):
            raise AmbiguousRunError('Unrecognized Dify response; inspect logs before retrying')
        data = result['data']
        return {'workflow_run_id': result.get('workflow_run_id') or data.get('id'),
                'task_id': result.get('task_id'), 'status': data.get('status'),
                'outputs': data.get('outputs'), 'total_tokens': data.get('total_tokens'),
                'server_elapsed_seconds': data.get('elapsed_time'), 'client_elapsed_seconds': time.perf_counter() - started,
                'started_at_utc': started_at, 'http_attempts': attempts}
