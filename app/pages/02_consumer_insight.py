import streamlit as st
from app.ui import context,heading,review_frame,run_action,csv_bytes,SENTIMENT

service,wid=context()
heading('消费者洞察','筛选评论，检查模型标签与引用，再选择少量评论运行真实分析。')
frame=review_frame(service,wid)
a,b,c=st.columns([1,1,2])
status=a.selectbox('分析状态',['全部','已分析','未分析','失败'])
sentiment=b.selectbox('模型情绪',['全部']+list(SENTIMENT))
keyword=c.text_input('评论关键词')
view=frame.copy()
if status=='已分析': view=view.loc[view.status.eq('validated')]
if status=='未分析': view=view.loc[view.status.eq('not_analyzed')]
if status=='失败': view=view.loc[~view.status.isin(['validated','not_analyzed'])]
if sentiment!='全部': view=view.loc[view.sentiment.eq(sentiment)]
if keyword: view=view.loc[view.review_text.str.contains(keyword,regex=False,na=False)]
st.caption(f'筛选后 {len(view)} 条 / 当前共 {len(frame)} 条；星级和日期字段不可用。')
st.dataframe(view[['review_id','review_text','sentiment','issue_labels','confidence','human_review_status']],hide_index=True,width='stretch')
st.download_button('下载当前筛选结果',csv_bytes(view),'consumer_reviews.csv','text/csv')
if len(view):
    ids=view.review_id.tolist()
    selected=st.selectbox('查看一条评论的完整证据',ids,format_func=lambda rid:frame.set_index('review_id').loc[rid,'review_text'][:55],key='detail_'+wid)
    record=next((r for r in service.analyses(wid) if r['review_id']==selected),None)
    if record: st.json(record,expanded=True)
    else: st.info('尚未分析；原始情感标签不会作为模型输入。')
    with st.expander('运行真实评论分析',expanded=status=='未分析'):
        chosen=st.multiselect('每次选择 1 至 5 条',ids,max_selections=5,format_func=lambda rid:frame.set_index('review_id').loc[rid,'review_text'][:55],key='analyze_ids_'+wid)
        st.caption('仅发送所选评论的 ID、脱敏正文、语言和品类。点击后可能产生费用；同一已完成请求会复用结果。')
        if st.button('分析所选评论（调用模型）',disabled=not chosen,type='primary'):
            run_action(service,wid,'review',chosen)
