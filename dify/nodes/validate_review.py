"""Self-contained Dify Code-node contract; no external dependencies or model simulation."""
import json
import math

PROMPT_VERSION = 'clothing-review-v1'
TAXONOMY = {
    'product_quality': ['material_quality', 'workmanship', 'damage', 'durability', 'color_fading', 'pilling'],
    'product_description': ['image_mismatch', 'spec_mismatch', 'missing_information'],
    'product_price': ['high_price', 'low_value', 'price_change'],
    'size_spec': ['too_small', 'too_large', 'length_mismatch', 'size_inconsistency'],
    'delivery': ['delay', 'packaging_damage', 'tracking_issue', 'wrong_or_missing_item'],
    'after_sales': ['refund_difficulty', 'return_exchange', 'slow_response'],
    'product_function': ['function_failure', 'performance_gap'],
    'shopping_experience': ['ordering_issue', 'communication_issue'],
    'other': ['specific_other_issue'],
}
ALLOWED_LABELS = {f'{parent}.{leaf}' for parent, leaves in TAXONOMY.items() for leaf in leaves}
SENTIMENTS = {'positive', 'neutral', 'negative', 'mixed', 'unknown'}
SCOPES = {'in_scope', 'out_of_scope', 'uncertain'}
FIELDS = {'review_id', 'scope_status', 'sentiment', 'sentiment_evidence', 'issues',
          'user_need', 'issue_summary', 'confidence', 'needs_review'}


def validate_input(review):
    fields = {'review_id', 'review_text', 'language', 'product_category'}
    if not isinstance(review, dict) or set(review) != fields:
        raise ValueError('input_fields_invalid')
    for key in fields:
        if not isinstance(review[key], str):
            raise ValueError('input_string_required')
    if not review['review_id'].strip() or len(review['review_id']) > 128:
        raise ValueError('review_id_invalid')
    if not review['review_text'].strip() or len(review['review_text']) > 4000:
        raise ValueError('review_text_empty_or_too_long')
    if review['language'] not in {'zh', 'en', 'pt'} or review['product_category'] != 'clothing':
        raise ValueError('language_or_category_invalid')
    return review


def validate_output(value, review):
    validate_input(review)
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('output_fields_invalid')
    if value['review_id'] != review['review_id']:
        raise ValueError('review_id_mismatch')
    if value['scope_status'] not in SCOPES or value['sentiment'] not in SENTIMENTS:
        raise ValueError('enum_invalid')
    for key in ['user_need', 'issue_summary']:
        if not isinstance(value[key], str) or len(value[key]) > 500:
            raise ValueError('summary_string_invalid')
    confidence = value['confidence']
    if type(confidence) not in {int, float} or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('confidence_invalid')
    if type(value['needs_review']) is not bool:
        raise ValueError('needs_review_boolean_required')
    text = review['review_text']
    evidence = value['sentiment_evidence']
    if not isinstance(evidence, list) or len(evidence) > 5:
        raise ValueError('sentiment_evidence_invalid')
    for quote in evidence:
        if not isinstance(quote, str) or not quote.strip() or quote not in text:
            raise ValueError('sentiment_evidence_not_in_source')
    if value['sentiment'] != 'unknown' and not evidence:
        raise ValueError('sentiment_evidence_required')
    issues = value['issues']
    if not isinstance(issues, list) or len(issues) > 10:
        raise ValueError('issues_array_invalid')
    labels = []
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {'label', 'evidence'}:
            raise ValueError('issue_fields_invalid')
        if issue['label'] not in ALLOWED_LABELS or issue['label'] in labels:
            raise ValueError('issue_label_invalid_or_duplicate')
        quote = issue['evidence']
        if not isinstance(quote, str) or not quote.strip() or quote not in text:
            raise ValueError('issue_evidence_not_in_source')
        labels.append(issue['label'])
    if value['sentiment'] == 'positive' and issues:
        raise ValueError('positive_cannot_have_negative_issue_labels')
    result = dict(value)
    # Confidence is a model self-report, never an empirically calibrated probability.
    result['needs_review'] = bool(value['needs_review'] or confidence < 0.8 or value['sentiment'] == 'unknown'
                                  or value['scope_status'] != 'in_scope')
    result['primary_category'] = sorted({label.split('.')[0] for label in labels})
    result['secondary_category'] = labels
    result['prompt_version'] = PROMPT_VERSION
    result['human_review_status'] = 'pending'
    return result


def main(llm_json: str, review_json: str) -> dict:
    """Dify output variable: result (String). Failure is not a genuine unknown classification."""
    review_id = ''
    try:
        review = json.loads(review_json)
        validate_input(review)
        review_id = review['review_id']
        if not isinstance(llm_json, str) or not llm_json.strip() or len(llm_json) > 20000:
            raise ValueError('llm_output_empty_or_too_large')
        value = validate_output(json.loads(llm_json), review)
        envelope = {'status': 'validated', 'review_id': review_id, 'analysis': value}
    except (ValueError, TypeError, KeyError) as error:
        # No original model output in error messages: it could contain secrets or invented text.
        code = str(error) if type(error) is ValueError and str(error).replace('_', '').isalnum() else 'invalid_json_or_types'
        envelope = {'status': 'validation_failed', 'review_id': review_id, 'error_code': code,
                    'needs_review': True, 'analysis': None}
    return {'result': json.dumps(envelope, ensure_ascii=False, allow_nan=False)}
