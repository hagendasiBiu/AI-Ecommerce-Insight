import pandas as pd
import plotly.express as px
import streamlit as st
from app.ui import context, heading, review_frame, issue_frame, COLORS, SENTIMENT

service,wid=context()
heading('从评论中发现核查线索','查看样本结构、模型分析覆盖情况，以及值得优先核查的问题。')
frame=review_frame(service,wid); evidence=service.get(wid,'evidence')
validated=frame.loc[frame.status.eq('validated')]
approved=[d for d in service.drafts(wid) if d['status']=='approved']
cols=st.columns(4)
for col,label,value in zip(cols,['当前评论','结构校验通过','问题类型','已批准核查计划'],[len(frame),len(validated),len((evidence or {}).get('issues',[])),len(approved)]):
    col.metric(label,f'{value:,}')
st.caption('以上均为当前工作区口径。模型标签未经人工金标准确认；批准数仅指核查计划。')
left,right=st.columns([1,1.4])
with left:
    st.subheader('模型情绪分布')
    counts=validated.sentiment.value_counts().rename_axis('sentiment').reset_index(name='评论数')
    if len(counts):
        counts['情绪']=counts.sentiment.map(SENTIMENT)
        chart=px.pie(counts,names='情绪',values='评论数',hole=.66,color_discrete_sequence=COLORS)
        chart.update_layout(height=340,margin=dict(t=10,b=10,l=10,r=10))
        st.plotly_chart(chart,width='stretch')
    else: st.info('当前还没有模型分析结果，请前往消费者洞察。')
with right:
    st.subheader('主要问题线索')
    issues=issue_frame(evidence)
    if len(issues):
        chart=px.bar(issues.sort_values('模型标记评论数'),x='模型标记评论数',y='问题',orientation='h',color_discrete_sequence=COLORS)
        chart.update_layout(height=340,margin=dict(t=10,b=10,l=10,r=10),xaxis=dict(dtick=1))
        st.plotly_chart(chart,width='stretch')
    else: st.info('分析后可在这里查看问题统计。')
st.subheader('继续工作')
a,b,c=st.columns(3)
with a: st.page_link('pages/02_consumer_insight.py',label='查看评论与原文证据',icon='💬')
with b: st.page_link('pages/05_strategy_center.py',label='诊断问题并审核策略',icon='🧭')
with c: st.page_link('pages/06_report_center.py',label='生成或下载核查报告',icon='📄')
with st.expander('数据范围与当前版本'):
    st.write('本地完整项目含二十条真实调试评论；公开代码包启动为空白工作区。没有真实商品、订单、金额和日期字段，不计算 GMV、星级差评率或时间趋势。上传数据单独建工作区。')
    st.write('当前语料来源平台和许可尚未确认，公开发布作品集前仍需核验或更换数据。')
