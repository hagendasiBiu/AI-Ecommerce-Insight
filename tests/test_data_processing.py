"""Integrity tests for cleaning decisions, privacy masking and heldout isolation."""
import unittest
import tempfile
from pathlib import Path
import pandas as pd
from src.data_processing import prepare_reviews, assign_splits, annotation_tasks, normalize_text, redact_contacts, run_cleaning
from src.business_metrics import keyword_mentions


def source(texts, labels=None):
    return pd.DataFrame({'cat': ['衣服'] * len(texts), 'label': labels or [1] * len(texts), 'review': texts})


class CleaningTests(unittest.TestCase):
    def test_conflict_quarantines_entire_group(self):
        clean, excluded, audit = prepare_reviews(source(['质量好！', '质量好', '独立文本'], [1, 0, 1]), 'hash')
        self.assertEqual(len(clean), 1)
        self.assertEqual(len(excluded), 2)
        self.assertEqual(len(audit), 3)

    def test_same_label_duplicate_keeps_first_and_original(self):
        clean, excluded, audit = prepare_reviews(source(['  尺码合适！ ', '尺码合适']), 'hash')
        self.assertEqual(clean.iloc[0]['review_text_original'], '  尺码合适！ ')
        self.assertEqual(excluded.iloc[0]['action'], 'deduplicate')
        self.assertEqual(clean.iloc[0]['source_row_number'], 1)

    def test_blank_invalid_and_punctuation_only(self):
        clean, excluded, _ = prepare_reviews(source([None, '  ', '！！！', '正常文字', '有效文本'], [1, 1, 0, 8, 1]), 'hash')
        self.assertEqual(len(clean), 1)
        self.assertEqual(len(excluded), 4)

    def test_negation_retained(self):
        self.assertEqual(normalize_text('  不好\u200b，\n不推荐！ '), '不好, 不推荐!')

    def test_category_flags_do_not_delete_or_relabel(self):
        clean, _, _ = prepare_reviews(source(['酒店质量很差'], [1]), 'hash')
        self.assertTrue(clean.iloc[0]['possible_category_noise'])
        self.assertEqual(clean.iloc[0]['source_label'], 1)

    def test_contacts_masked(self):
        self.assertEqual(redact_contacts('联系13812345678或a@example.com'), '联系[PHONE]或[EMAIL]')

    def test_missing_columns_rejected(self):
        with self.assertRaises(ValueError):
            prepare_reviews(pd.DataFrame({'review': ['衣服']}), 'hash')


class SplitTests(unittest.TestCase):
    def setUp(self):
        texts = [f'这条服饰评论编号{i}' for i in range(400)]
        self.clean, _, _ = prepare_reviews(source(texts, [0] * 200 + [1] * 200), 'hash')

    def test_sizes_and_no_overlap(self):
        split = assign_splits(self.clean)
        self.assertEqual(split['split'].value_counts().to_dict(), {'prompt_dev': 200, 'development_pool': 100, 'heldout_test': 100})
        self.assertEqual(split['fingerprint'].nunique(), len(split))
        for label in [0, 1]:
            self.assertEqual(len(split.loc[split['split'].eq('heldout_test') & split['source_label'].eq(label)]), 50)

    def test_reordered_input_same_assignment(self):
        first = assign_splits(self.clean).set_index('review_id')['split'].to_dict()
        second = assign_splits(self.clean.sample(frac=1, random_state=9)).set_index('review_id')['split'].to_dict()
        self.assertEqual(first, second)

    def test_annotation_tasks_blind_and_pending(self):
        tasks = annotation_tasks(assign_splits(self.clean))
        self.assertNotIn('source_label', tasks.columns)
        self.assertNotIn('split', tasks.columns)
        self.assertTrue(tasks['sentiment'].eq('').all())
        self.assertTrue(tasks['annotation_status'].eq('pending').all())

    def test_insufficient_sample_fails(self):
        with self.assertRaises(ValueError):
            assign_splits(self.clean.iloc[:10])

    def test_keyword_count_is_not_negative_count(self):
        mentions = keyword_mentions(pd.DataFrame({'review_text': ['质量好质量好', '质量差', '颜色漂亮']})).set_index('topic')
        self.assertEqual(mentions.loc['质量与做工', 'mention_reviews'], 2)
        self.assertEqual(mentions.loc['质量与做工', 'denominator'], 3)

    def test_rerun_preserves_human_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'data/raw/chinese_reviews'
            raw.mkdir(parents=True)
            source([f'服饰测试文本{i}' for i in range(400)], [0] * 200 + [1] * 200).to_csv(
                raw / 'online_shopping_10_cats.csv', index=False)
            run_cleaning(root)
            path = root / 'data/sample/annotation_prompt_dev.csv'
            tasks = pd.read_csv(path, keep_default_na=False)
            tasks.loc[0, 'sentiment'] = 'unknown'
            tasks.loc[0, 'annotation_status'] = 'completed'
            tasks.to_csv(path, index=False)
            before = path.read_bytes()
            run_cleaning(root)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
