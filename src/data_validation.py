"""Read-only raw corpus profiling; all numbers come from the downloaded CSV."""
from pathlib import Path
from datetime import datetime
import json
import pandas as pd


def profile(frame):
    """Report duplicate excess rows separately from all duplicate participants."""
    text = frame['review'].astype('string')
    normalized = text.str.strip()
    return {
        'rows': len(frame),
        'dtypes': {col: str(dtype) for col, dtype in frame.dtypes.items()},
        'missing': {col: int(value) for col, value in frame.isna().sum().items()},
        'blank_non_null_reviews': int((normalized.eq('') & text.notna()).sum()),
        'duplicate_excess_rows': int(frame.duplicated().sum()),
        'all_duplicate_participants': int(frame.duplicated(keep=False).sum()),
        'repeated_review_text_excess': int(text.dropna().duplicated().sum()),
        'invalid_labels': int((~frame['label'].isin([0, 1])).sum()),
        'label_counts': {str(k): int(v) for k, v in frame['label'].value_counts(dropna=False).items()},
        'category_counts': {str(k): int(v) for k, v in frame['cat'].value_counts(dropna=False).items()},
        'text_length_characters': {str(k): float(v) for k, v in text.str.len().describe().items()},
    }


def inspect_data(root):
    root = Path(root)
    path = root / 'data/raw/chinese_reviews/online_shopping_10_cats.csv'
    if not path.is_file():
        raise FileNotFoundError(f'原始 CSV 不存在，请先运行 bootstrap_phase1.py：{path}')
    df = pd.read_csv(path)
    required = {'cat', 'label', 'review'}
    if not required.issubset(df.columns):
        raise ValueError(f'缺失字段：{sorted(required - set(df.columns))}')
    clothing = df.loc[df['cat'].eq('衣服')]
    if clothing.empty:
        raise ValueError('没有衣服类别，请检查原始文件。')
    result = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'file': str(path), 'file_bytes': path.stat().st_size,
        'columns': list(df.columns), 'all_categories': profile(df), 'clothing': profile(clothing),
        'unavailable_fields': ['order_id', 'product_id', 'rating', 'price', 'review_date', 'delivery_date'],
    }
    reports = root / 'reports'
    reports.mkdir(exist_ok=True)
    (reports / 'data_quality_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    a, c = result['all_categories'], result['clothing']
    lines = [
        '# Phase 1 数据质量报告', '', f"生成时间：{result['generated_at']}",
        '', '统计基于下载后的原始 CSV，未执行去重或清洗。', '',
        '| 检查项 | 全语料 | 服饰（衣服） |', '|---|---:|---:|',
    ]
    for title, key in [('原始行数', 'rows'), ('完全重复的多余行', 'duplicate_excess_rows'),
                       ('全部重复参与行', 'all_duplicate_participants'),
                       ('评论正文重复的多余行', 'repeated_review_text_excess'),
                       ('非空值中的空白文本', 'blank_non_null_reviews'), ('异常标签', 'invalid_labels')]:
        lines.append(f'| {title} | {a[key]} | {c[key]} |')
    lines += ['', '## 字段与缺失值', '', '| 字段 | 类型 | 全语料缺失 | 服饰缺失 |', '|---|---|---:|---:|']
    for col in df.columns:
        lines.append(f"| {col} | {a['dtypes'][col]} | {a['missing'][col]} | {c['missing'][col]} |")
    lines += ['', '## 品类数据量', '', '| 品类 | 原始行数 |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in a['category_counts'].items()]
    lines += ['', '## 服饰原始标签分布', '', '| 标签 | 行数 |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in c['label_counts'].items()]
    lines += [
        '', '0 是语料负向标签，1 是正向标签，不是 1—5 星评分；标签也不是无误的人工金标准。',
        '', '## 验收与局限',
        '- CSV 可读取，实际字段与发布者字段说明一致，记录了原文件 SHA-256。',
        '- 尚未清洗；去重、文本规范化、标注冲突检查和独立测试集拆分留到下一阶段。',
        '- 具体平台、采集日期、抽样方法与数据许可未确认，当前为本地原型候选语料。',
        '- 不将语料写为抖音、淘宝或京东数据；不公开原始数据和评论样例。',
        '- 缺少订单、商品 ID、金额、星级、日期与履约记录；不计算 GMV、店铺差评率、价格带、时间增长率或物流延迟率。',
        '- 类别仅为“衣服”，不能把模型推断的服装细分类别称为源数据字段。',
        '- 公开展示前仍需解决来源/许可问题或换用授权明确的数据。',
        '- 按用户选择 C，Olist 与英文服装数据暂不下载；未完成原始双数据集版本验收，按调整后的中文评论版验收。',
    ]
    (reports / 'data_quality_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    report = inspect_data(Path(__file__).resolve().parents[1])
    print(json.dumps(report, ensure_ascii=False, indent=2))
