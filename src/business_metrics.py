"""Descriptive corpus metrics only. Keyword mentions are not AI classifications."""
import pandas as pd

KEYWORDS = {
    '尺码与版型': ['尺码', '大小', '裤长', '裤脚', '腰围', '修身', '合身', '版型'],
    '面料与舒适度': ['面料', '布料', '材质', '舒服', '舒适', '透气', '扎人'],
    '质量与做工': ['质量', '做工', '掉色', '褪色', '起球', '开线', '线头', '破洞'],
    '描述与实物': ['色差', '图片', '照片', '描述', '实物', '不符'],
    '价格与价值': ['价格', '价钱', '便宜', '贵', '性价比', '物有所值'],
    '配送体验': ['物流', '快递', '发货', '送货', '包装'],
    '客服与退换': ['客服', '售后', '退货', '换货', '退款', '退换'],
}


def keyword_mentions(frame):
    """A review counts once per topic. Topics overlap. Count both positive and negative wording."""
    records = []
    text = frame['review_text'].fillna('')
    for topic, words in KEYWORDS.items():
        mask = text.map(lambda t: any(w in t for w in words))
        records.append({'topic': topic, 'mention_reviews': int(mask.sum()), 'denominator': len(frame),
                        'mention_share': float(mask.mean()) if len(frame) else None,
                        'method': 'keyword_literal_match_v1'})
    return pd.DataFrame(records).sort_values('mention_reviews', ascending=False).reset_index(drop=True)


def length_distribution(frame):
    bands = pd.cut(frame['text_length'], bins=[0, 10, 20, 50, 100, float('inf')],
                   labels=['1–10', '11–20', '21–50', '51–100', '101+'], right=True)
    return bands.value_counts(sort=False).rename_axis('characters').rename('reviews').reset_index()
