import streamlit as st
from app.ui import context,heading

service,wid=context()
heading('履约线索','从评论追溯配送体验，明确下一步需要什么业务资料。')
evidence=service.get(wid,'evidence')
issues=[i for i in (evidence or {}).get('issues',[]) if i['issue_label'].startswith('delivery.')]
st.metric('模型标记的配送问题类型',len(issues))
for issue in issues:
    with st.container(border=True):
        st.subheader(issue['issue_label'])
        st.write(f"{issue['review_count']} 条评论提及；分母为 {issue['denominator']} 条有效样本。尚未人工确认。")
        for ref in issue['evidence']:
            st.write('原文证据：'+ref['quote'])
            st.caption('评论 ID：'+ref['review_id'])
if not issues: st.info('当前已分析样本没有标记配送问题；不能据此推断履约没有问题。')
st.subheader('补充资料后才能计算的指标')
st.dataframe([{'待验证指标':'实际配送时长','必要字段':'购买时间、实际送达时间、订单状态'},
              {'待验证指标':'延迟送达率','必要字段':'订单 ID、预计及实际送达时间、已送达状态'},
              {'待验证指标':'配送与评分关系','必要字段':'订单-评论关联、星级评分；只能先分析相关性'}],hide_index=True,width='stretch')
st.write('当前工作区没有订单与履约记录。本页不把评论中的“物流慢”直接当作真实延迟订单，也不生成模拟物流指标。')
