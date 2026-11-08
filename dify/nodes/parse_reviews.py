"""Paste into the Dify batch input Code node; standalone standard-library Python."""
import json


def main(reviews_json: str) -> dict:
    if not isinstance(reviews_json, str) or len(reviews_json) > 30000:
        raise ValueError('Batch input must be a JSON string of at most 30000 characters')
    reviews = json.loads(reviews_json)
    if not isinstance(reviews, list) or not 1 <= len(reviews) <= 5:
        raise ValueError('Use 1 to 5 reviews per batch during the pilot')
    ids = set()
    items = []
    for review in reviews:
        if not isinstance(review, dict) or set(review) != {'review_id', 'review_text', 'language', 'product_category'}:
            raise ValueError('Unexpected input fields; never send source labels or private audit data')
        if any(not isinstance(review[k], str) for k in review):
            raise ValueError('All input fields must be strings')
        if not review['review_id'].strip() or len(review['review_id']) > 128 or review['review_id'] in ids:
            raise ValueError('Review IDs must be nonempty, unique and at most 128 characters')
        if not review['review_text'].strip() or len(review['review_text']) > 4000:
            raise ValueError('Review text must contain 1 to 4000 characters')
        if review['language'] not in {'zh', 'en', 'pt'} or review['product_category'] != 'clothing':
            raise ValueError('Unsupported language or category')
        ids.add(review['review_id'])
        items.append(json.dumps(review, ensure_ascii=False))
    return {'reviews': items, 'batch_size': len(items)}
