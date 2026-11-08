"""Shared UI framing and display transforms. No model calls during rendering."""
from pathlib import Path
import pandas as pd
import streamlit as st
from src.app_service import AppService

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'product_quality.color_fading':'褪色反馈','other.specific_other_issue':'其他具体问题',
         'product_description.image_mismatch':'图片与实物差异','delivery.delay':'物流慢反馈',
         'product_price.low_value':'价值感反馈','product_quality.material_quality':'面料问题',
         'size_spec.length_mismatch':'长度不合适'}
SENTIMENT = {'positive':'正向','negative':'负向','mixed':'混合','neutral':'中性','unknown':'信息不足'}
COLORS = ['#176D86','#E9A04C','#6087BA','#A0BDCA']


def context():
    return AppService(ROOT), st.session_state['workspace_id']


def heading(title, detail):
    st.caption('AI E-COMMERCE INSIGHT / 服饰消费者研究')
    st.title(title)
    st.write(detail)


def review_frame(service, wid):
    results = {r['review_id']: r for r in service.analyses(wid)}
    rows = []
    for review in service.reviews(wid):
        result = results.get(review['review_id'], {})
        analysis = result.get('analysis') or {}
        rows.append({**review, 'status': result.get('status','not_analyzed'),
                     'sentiment': analysis.get('sentiment','not_analyzed'),
                     'scope_status': analysis.get('scope_status',''),
                     'issue_labels': ' / '.join(i['label'] for i in analysis.get('issues',[])),
                     'confidence': analysis.get('confidence'),
                     'human_review_status': analysis.get('human_review_status','not_analyzed')})
    return pd.DataFrame(rows,columns=['review_id','review_text','language','product_category','status',
        'sentiment','scope_status','issue_labels','confidence','human_review_status'])


def issue_frame(evidence):
    return pd.DataFrame([{'问题':NAMES.get(i['issue_label'],i['issue_label']), '模型标记评论数':i['review_count'],
                          '样本内占比':i['sample_share'], '优先级分数':i['priority_score'],
                          '核查分组':i['priority_band']} for i in (evidence or {}).get('issues',[])])


def run_action(service, wid, kind, ids=None):
    try:
        with st.spinner('正在调用工作流，请勿重复点击。超时后先检查平台日志。'):
            result = service.call(wid,kind,ids)
        st.success('已复用本地运行记录。' if result.get('reused') else '真实调用完成，结果已保存。')
        st.rerun()
    except Exception as error:
        # Do not surface arbitrary upstream traceback/messages containing private inputs.
        if isinstance(error, ValueError):
            st.error(str(error))
        else:
            st.error('调用未完成。请检查本地配置与 Dify 日志；已有请求记录时不要反复重试。')


def csv_bytes(frame):
    result = frame.copy()
    for col in result.select_dtypes(include=['object','str']).columns:
        result[col] = result[col].map(lambda x: "'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x)
    return result.to_csv(index=False).encode('utf-8-sig')
