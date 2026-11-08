"""Local validation uses the exact same source as the Dify validation Code node."""
import importlib.util
import json
from pathlib import Path

NODE = Path(__file__).resolve().parents[1] / 'dify/nodes/validate_review.py'
spec = importlib.util.spec_from_file_location('dify_review_contract', NODE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
PROMPT_VERSION = contract.PROMPT_VERSION


def validate_batch_response(outputs, reviews):
    """Require positional correspondence. Never silently drop null/failed iteration results."""
    if not isinstance(outputs, dict) or not isinstance(outputs.get('results'), list):
        raise ValueError('Dify End output must contain results: array[string]')
    results = outputs['results']
    if len(results) != len(reviews):
        raise ValueError('Dify result count mismatch; do not remove failed iteration items')
    checked = []
    for result, review in zip(results, reviews):
        if result is None:
            checked.append({'status': 'workflow_item_failed', 'review_id': review['review_id'], 'analysis': None})
            continue
        envelope = json.loads(result) if isinstance(result, str) else result
        if not isinstance(envelope, dict) or envelope.get('review_id') != review['review_id']:
            raise ValueError('Dify returned an unknown or misordered review ID')
        if envelope.get('status') == 'validated':
            analysis = envelope.get('analysis')
            if not isinstance(analysis, dict):
                raise ValueError('Missing analysis')
            raw_fields = {key: value for key, value in analysis.items() if key in contract.FIELDS}
            canonical = contract.validate_output(raw_fields, review)
            checked.append({'status': 'validated', 'review_id': review['review_id'], 'analysis': canonical})
        elif envelope.get('status') == 'validation_failed':
            checked.append({'status': 'validation_failed', 'review_id': review['review_id'],
                            'analysis': None, 'needs_review': True,
                            'error_code': str(envelope.get('error_code', 'unspecified'))[:100]})
        else:
            raise ValueError('Unexpected Dify result status')
    return checked
