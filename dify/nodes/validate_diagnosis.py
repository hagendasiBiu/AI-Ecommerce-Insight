"""Self-contained Dify diagnosis Code node. Verify referenced facts; no invented statistics."""
import json
import re


def validate_diagnosis(value, evidence):
    if not isinstance(evidence, dict) or not isinstance(evidence.get('facts'), dict) or not isinstance(evidence.get('issues'), list):
        raise ValueError('input_evidence_invalid')
    if not isinstance(value, dict) or set(value) != {'evidence_id', 'findings', 'limitations'}:
        raise ValueError('diagnosis_fields_invalid')
    if value['evidence_id'] != evidence.get('evidence_id'):
        raise ValueError('evidence_id_mismatch')
    if not isinstance(value['findings'], list) or len(value['findings']) > 5:
        raise ValueError('findings_array_invalid')
    def prose(text, max_length=500):
        if not isinstance(text, str) or not text.strip() or len(text) > max_length:
            raise ValueError('prose_string_invalid')
        # All quantitative facts are renderer-owned registry values. No prose figures.
        if re.search(r'[0-9０-９%％]', text):
            raise ValueError('put_quantitative_facts_in_fact_ids_not_prose')
    index = {i['issue_label']: i for i in evidence['issues']}
    ids, labels = set(), set()
    for finding in value['findings']:
        required = {'finding_id', 'issue_label', 'fact_ids', 'evidence_review_ids', 'possible_causes', 'next_validation'}
        if not isinstance(finding, dict) or set(finding) != required:
            raise ValueError('finding_fields_invalid')
        fid = finding['finding_id']
        if not isinstance(fid, str) or not re.fullmatch(r'D[1-9][0-9]?', fid) or fid in ids:
            raise ValueError('finding_id_invalid')
        ids.add(fid)
        label = finding['issue_label']
        if label not in index or label in labels:
            raise ValueError('issue_label_missing_or_duplicate')
        labels.add(label)
        issue = index[label]
        fact_ids = finding['fact_ids']
        if not isinstance(fact_ids, list) or not fact_ids or len(fact_ids) != len(set(fact_ids)):
            raise ValueError('fact_ids_invalid')
        if any(key not in issue['fact_ids'] or key not in evidence['facts'] for key in fact_ids):
            raise ValueError('unrecognized_or_wrong_issue_fact_id')
        refs = finding['evidence_review_ids']
        allowed = {e['review_id'] for e in issue['evidence']}
        if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)) or not set(refs).issubset(allowed):
            raise ValueError('evidence_review_ids_invalid')
        causes = finding['possible_causes']
        if not isinstance(causes, list) or not 1 <= len(causes) <= 3:
            raise ValueError('causes_array_invalid')
        for cause in causes:
            if not isinstance(cause, dict) or set(cause) != {'hypothesis', 'status'} or cause['status'] != 'unverified':
                raise ValueError('causes_must_be_unverified_hypotheses')
            prose(cause['hypothesis'])
        prose(finding['next_validation'])
    if not isinstance(value['limitations'], list) or not value['limitations']:
        raise ValueError('limitations_required')
    for text in value['limitations']:
        prose(text)
    result = dict(value)
    result['human_review_status'] = 'pending'
    result['source_review_status'] = evidence.get('human_review_status', 'pending')
    result['scope'] = evidence.get('scope')
    result['mandatory_limitations'] = evidence.get('limitations', [])
    result['prompt_version'] = 'business-diagnosis-v1'
    return result


def main(llm_json: str, metrics_json: str) -> dict:
    try:
        if not isinstance(llm_json, str) or not llm_json.strip() or len(llm_json) > 30000:
            raise ValueError('llm_output_empty_or_too_large')
        if not isinstance(metrics_json, str) or len(metrics_json) > 150000:
            raise ValueError('metrics_input_too_large')
        evidence = json.loads(metrics_json)
        diagnosis = validate_diagnosis(json.loads(llm_json), evidence)
        envelope = {'status': 'validated', 'diagnosis': diagnosis, 'error_code': None}
    except (ValueError, TypeError, KeyError) as error:
        code = str(error) if type(error) is ValueError and str(error).replace('_', '').isalnum() else 'invalid_json_or_types'
        envelope = {'status': 'validation_failed', 'diagnosis': None, 'error_code': code, 'needs_review': True}
    return {'result': json.dumps(envelope, ensure_ascii=False, allow_nan=False)}
