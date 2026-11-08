"""Phase 2: conservative cleaning, source-row audit, deterministic group-safe split."""
from pathlib import Path
import hashlib
import re
import unicodedata
import pandas as pd

VERSION = 'clean-v1'
SPLIT_SEED = 'clothing-v1-20261106'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def normalize_text(value):
    """Keep original semantics/punctuation; standardize width and whitespace only."""
    if pd.isna(value):
        return ''
    text = unicodedata.normalize('NFKC', str(value))
    text = re.sub('[\u200b\u200c\u200d\ufeff]', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def fingerprint(text):
    """Conservative duplicate grouping: ignore punctuation/spacing, retain letters/numbers."""
    return ''.join(ch.lower() for ch in text if ch.isalnum())


def redact_contacts(text):
    """Mask common email/mobile patterns; this is not comprehensive PII detection."""
    text = re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[EMAIL]', text)
    return re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', '[PHONE]', text)


def prepare_reviews(raw, source_hash):
    required = {'cat', 'label', 'review'}
    if not required.issubset(raw.columns):
        raise ValueError(f'Missing source fields: {sorted(required - set(raw.columns))}')
    frame = raw.copy().reset_index(drop=True)
    # CSV data row 1 means the first row after the header; not a byte/line offset.
    frame['source_row_number'] = frame.index + 1
    frame = frame.loc[frame['cat'].eq('衣服')].copy()
    if frame.empty:
        raise ValueError('No clothing records')
    frame = frame.rename(columns={'review': 'review_text_original', 'label': 'source_label', 'cat': 'source_category'})
    frame['source_file_sha256'] = source_hash
    frame['source_row_id'] = frame['source_row_number'].map(lambda n: digest(f'{source_hash}:{n}'))
    frame['review_text_normalized'] = frame['review_text_original'].map(normalize_text)
    frame['fingerprint'] = frame['review_text_normalized'].map(fingerprint)
    frame['review_id'] = frame['fingerprint'].map(lambda t: digest(f'clothing:{t}'))
    frame['review_text'] = frame['review_text_normalized'].map(redact_contacts)
    frame['text_length'] = frame['review_text_normalized'].str.len()
    frame['cleaning_version'] = VERSION
    frame['action'] = 'keep'
    frame['reason'] = ''
    def exclude(mask, reason):
        active = mask & frame['action'].eq('keep')
        frame.loc[active, 'action'] = 'quarantine'
        frame.loc[active, 'reason'] = reason
    exclude(frame['fingerprint'].eq(''), 'empty_or_no_alphanumeric_text')
    exclude(~frame['source_label'].isin([0, 1]), 'invalid_source_label')
    eligible = frame.loc[frame['action'].eq('keep')]
    conflicts = eligible.groupby('fingerprint')['source_label'].nunique()
    conflict_keys = set(conflicts[conflicts.gt(1)].index)
    exclude(frame['fingerprint'].isin(conflict_keys), 'conflicting_source_labels_in_text_group')
    eligible = frame.loc[frame['action'].eq('keep')]
    duplicate_indices = eligible.index[eligible['fingerprint'].duplicated(keep='first')]
    frame.loc[duplicate_indices, 'action'] = 'deduplicate'
    frame.loc[duplicate_indices, 'reason'] = 'same_label_text_group_keep_first_source_row'
    # Keywords only flag review candidates. They neither correct source categories nor label sentiment.
    frame['possible_category_noise'] = frame['review_text_normalized'].str.contains(
        r'洗发水|护发素|手机屏幕|充电器|热水器|酒店|水果|苹果手机|电脑主机', regex=True)
    frame['short_text'] = frame['text_length'].lt(10)
    frame['contact_redacted'] = frame['review_text'].ne(frame['review_text_normalized'])
    frame['needs_manual_review'] = frame[['possible_category_noise', 'short_text', 'contact_redacted']].any(axis=1)
    clean = frame.loc[frame['action'].eq('keep')].copy()
    quarantine = frame.loc[~frame['action'].eq('keep')].copy()
    return clean.reset_index(drop=True), quarantine.reset_index(drop=True), frame.reset_index(drop=True)


def assign_splits(clean, dev_per_label=100, test_per_label=50):
    """Select by deterministic hash within proxy source-label strata, never by row order."""
    frame = clean.copy()
    frame['sampling_hash'] = frame['review_id'].map(lambda x: digest(f'{SPLIT_SEED}:{x}'))
    frame['split'] = 'development_pool'
    for label in [0, 1]:
        indices = frame.loc[frame['source_label'].eq(label)].sort_values(['sampling_hash', 'review_id']).index
        if len(indices) < dev_per_label + test_per_label:
            raise ValueError(f'Insufficient records for source-label stratum {label}')
        frame.loc[indices[:test_per_label], 'split'] = 'heldout_test'
        frame.loc[indices[test_per_label:test_per_label + dev_per_label], 'split'] = 'prompt_dev'
    return frame.sort_values('source_row_number').reset_index(drop=True)


def annotation_tasks(frame):
    """Blind task export: omit proxy labels, original text, hashes and model predictions."""
    tasks = frame.sort_values('sampling_hash')[['review_id', 'review_text', 'needs_manual_review']].copy()
    for col in ['scope_status', 'sentiment', 'issue_labels_json', 'evidence_json', 'user_need',
                'annotator_id', 'annotation_seconds', 'notes', 'reviewer_id', 'review_status']:
        tasks[col] = ''
    tasks['annotation_status'] = 'pending'
    return tasks


def run_cleaning(root):
    root = Path(root)
    source = root / 'data/raw/chinese_reviews/online_shopping_10_cats.csv'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    clean, quarantine, audit = prepare_reviews(pd.read_csv(source), source_hash)
    split = assign_splits(clean)
    output = root / 'data/processed'
    samples = root / 'data/sample'
    output.mkdir(parents=True, exist_ok=True)
    samples.mkdir(parents=True, exist_ok=True)
    for name, table in [('clothing_clean', split), ('clothing_quarantine', quarantine), ('cleaning_audit', audit)]:
        table.to_csv(output / f'{name}.csv', index=False, encoding='utf-8-sig')
    # Future prompt tuning must read this pool, not clothing_clean (which includes heldout rows).
    split.loc[~split['split'].eq('heldout_test')].to_csv(output / 'development_pool.csv', index=False, encoding='utf-8-sig')
    split[['review_id', 'source_row_id', 'source_row_number', 'source_label', 'split', 'sampling_hash']].to_csv(
        output / 'split_manifest_private.csv', index=False, encoding='utf-8-sig')
    for name, value in [('annotation_prompt_dev', 'prompt_dev'), ('annotation_heldout_test', 'heldout_test')]:
        target = samples / f'{name}.csv'
        # Never overwrite human annotations on rerun. Changed IDs require explicit migration.
        tasks = annotation_tasks(split.loc[split['split'].eq(value)])
        if target.exists():
            existing = pd.read_csv(target)
            if existing['review_id'].tolist() != tasks['review_id'].tolist():
                raise ValueError(f'Existing annotation task IDs changed: {target}')
        else:
            tasks.to_csv(target, index=False, encoding='utf-8-sig')
    return split, quarantine, audit
