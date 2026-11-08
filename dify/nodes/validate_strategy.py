"""Standalone Dify strategy validator. Output remains a hypothesis awaiting human approval."""
import json
import re


def validate_strategy(value, bundle):
    evidence, diagnosis = bundle['evidence'], bundle['diagnosis']
    if diagnosis['evidence_id'] != evidence['evidence_id']:
        raise ValueError('input_evidence_mismatch')
    if not isinstance(value, dict) or set(value) != {'evidence_id', 'strategies'} or value['evidence_id'] != evidence['evidence_id']:
        raise ValueError('strategy_fields_or_evidence_id_invalid')
    if not isinstance(value['strategies'], list) or not 1 <= len(value['strategies']) <= 5:
        raise ValueError('strategies_array_invalid')
    findings = {f['finding_id']: f for f in diagnosis['findings']}
    ids, finding_ids = set(), set()
    for strategy in value['strategies']:
        required = {'strategy_id', 'finding_id', 'fact_ids', 'action', 'owner_function', 'target_metric',
                    'validation_design', 'validation_days', 'guardrail', 'target_direction', 'limitations', 'effect_status'}
        if not isinstance(strategy, dict) or set(strategy) != required:
            raise ValueError('strategy_item_fields_invalid')
        sid, fid = strategy['strategy_id'], strategy['finding_id']
        if not isinstance(sid, str) or not re.fullmatch(r'S[1-9][0-9]?', sid) or sid in ids:
            raise ValueError('strategy_id_invalid')
        if fid not in findings or fid in finding_ids:
            raise ValueError('finding_id_unknown_or_duplicate')
        ids.add(sid)
        finding_ids.add(fid)
        refs = strategy['fact_ids']
        if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
            raise ValueError('fact_ids_invalid')
        if any(ref not in findings[fid]['fact_ids'] or ref not in evidence['facts'] for ref in refs):
            raise ValueError('fact_reference_invalid')
        for key in ['action', 'owner_function', 'target_metric', 'validation_design', 'guardrail']:
            text = strategy[key]
            if not isinstance(text, str) or not text.strip() or len(text) > 700:
                raise ValueError('strategy_prose_invalid')
            if re.search(r'[0-9０-９%％]', text):
                raise ValueError('unsupported_quantitative_prose')
        if type(strategy['validation_days']) is not int or not 7 <= strategy['validation_days'] <= 90:
            raise ValueError('planned_validation_days_invalid')
        if strategy['target_direction'] not in {'decrease', 'increase', 'clarify'} or strategy['effect_status'] != 'hypothesis_only':
            raise ValueError('effect_must_be_hypothesis')
        if not isinstance(strategy['limitations'], list) or not strategy['limitations']:
            raise ValueError('limitations_required')
        for text in strategy['limitations']:
            if not isinstance(text, str) or not text.strip() or len(text) > 500 or re.search(r'[0-9０-９%％]', text):
                raise ValueError('limitation_invalid')
    result = dict(value)
    result.update(human_review_status='pending', source_review_status=evidence.get('human_review_status', 'pending'),
                  scope='exploratory_development_sample_only', prompt_version='strategy-generation-v1')
    return result


def main(llm_json: str, strategy_json: str) -> dict:
    try:
        if not isinstance(llm_json, str) or not llm_json.strip() or len(llm_json) > 40000:
            raise ValueError('model_output_empty_or_too_large')
        if not isinstance(strategy_json, str) or len(strategy_json) > 180000:
            raise ValueError('strategy_input_invalid')
        result = validate_strategy(json.loads(llm_json), json.loads(strategy_json))
        envelope = {'status': 'validated', 'strategy_plan': result, 'error_code': None}
    except (ValueError, TypeError, KeyError) as error:
        code = str(error) if type(error) is ValueError and str(error).replace('_', '').isalnum() else 'invalid_json_or_types'
        envelope = {'status': 'validation_failed', 'strategy_plan': None, 'error_code': code, 'needs_review': True}
    return {'result': json.dumps(envelope, ensure_ascii=False, allow_nan=False)}
