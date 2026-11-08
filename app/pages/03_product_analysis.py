import pandas as pd
import streamlit as st
import plotly.express as px
from app.ui import context,heading,issue_frame,COLORS
from src.strategy_engine import sensitivity_table

service,wid=context()
heading('问题与核查优先级','从模型标记的问题出发，核对支持数、分母和排序口径。')
evidence=service.get(wid,'evidence')
if not evidence or not evidence['issues']:
    st.info('尚无可用问题证据。先在消费者洞察中运行评论分析。')
else:
    issues=issue_frame(evidence)
    st.dataframe(issues,hide_index=True,width='stretch',column_config={'样本内占比':st.column_config.NumberColumn(format='percent'),'优先级分数':st.column_config.NumberColumn(format='%.3f')})
    st.caption(f"统计分母 {evidence['validated_in_scope_known_sentiment_reviews']} 条；问题可重叠，支持数少于三条先人工核查。")
    with st.expander('查看计算方法',expanded=True):
        st.latex(r'P=\frac{7}{13}F+\frac{6}{13}N')
        st.write('F：问题评论数 / 样本内最多问题评论数。N：该问题严格负向评论数 / 该问题评论数，混合情绪另列。缺少增长率和关注度字段，不填零。')
        st.write('分数是探索性核查顺序，不是损失或收益。原始数据没有商品 ID、价格和评分，因此不显示商品排名、价格带或品类满意度。')
    table=sensitivity_table(evidence)
    chart=px.line(table,x='F_weight',y='rank',color='issue_label',markers=True,labels={'F_weight':'频率权重','rank':'并列名次','issue_label':'问题'})
    chart.update_yaxes(autorange='reversed',dtick=1)
    st.plotly_chart(chart,width='stretch')
    st.caption('三组权重仅作样本内敏感性检查，不证明外部有效性。')
