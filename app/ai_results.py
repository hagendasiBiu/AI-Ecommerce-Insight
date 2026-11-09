"""AI-only study view, clearly separated from the optional human annotation archive."""
import json
import pandas as pd
import streamlit as st
from src.evaluation import AnnotationStore


def render_ai_results(root):
    data=json.loads((root/'data/processed/ai_annotations_final.json').read_text(encoding='utf-8'))
    summary=data['summary']
    st.success('AI 代标已完成。你不需要继续逐条标注。')
    st.caption('根据用户选择改为 AI 代标研究；原保留集不再被称为独立人工金标准测试。')
    human=AnnotationStore(root)
    human_n=sum(human.progress(s)['reviewed'] for s in ['prompt_dev','heldout_test'])
    columns=st.columns(4)
    for column,label,value in zip(columns,['AI 标注覆盖','首次契约通过','AI 补充标注','用户已复核记录'],
        [f"{summary['completed_ai_annotations']}/{summary['task_count']}",
         f"{summary['first_pass_validated_count']}/{summary['task_count']}",str(summary['codex_supplemental_count']),str(human_n)]):
        column.metric(label,value)
    st.info('首次通过率检查结构、枚举和原文引用，不是模型准确率。补充标注由 AI 完成，不计作人工复核。')
    def select_ai_workspace():
        # A callback runs before widgets are built, so the sidebar does not
        # reapply the old selection during the next rerun.
        st.session_state.workspace_id=data['workspace_id']
        st.session_state.workspace_picker=data['workspace_id']
    st.button('打开 300 条研究工作区',on_click=select_ai_workspace)
    rows=[]
    for rid,item in data['items'].items():
        analysis=item.get('analysis') or {}
        rows.append({'review_id':rid,'范围':analysis.get('scope_status'),'情感':analysis.get('sentiment'),
            '问题标签':' / '.join(i['label'] for i in analysis.get('issues',[])),
            '标注来源':item.get('provenance','AI'),'人工复核':'未复核','建议复核':analysis.get('needs_review')})
    st.subheader('AI 标注结果')
    filter_value=st.selectbox('标注来源',['全部','real_dify_workflow','phase4_record_reused','codex_supplemental_annotation'])
    frame=pd.DataFrame(rows)
    if filter_value!='全部': frame=frame.loc[frame['标注来源'].eq(filter_value)]
    st.dataframe(frame,hide_index=True,width='stretch')
    csv=root/'data/processed/ai_annotations_300.csv'
    if csv.exists(): st.download_button('下载本地 300 条 AI 标注 CSV',csv.read_bytes(),'ai_annotations_300.csv','text/csv')
    st.caption('CSV 包含源评论，只供本地使用；原语料许可未确认，不进入公开代码仓库。')
    with st.expander('流程、弱标签一致性和耗时'):
        st.write('首次契约通过率：'+f"{summary['first_pass_contract_pass_rate']:.2%}")
        st.write('补充后的源弱标签一致率：'+f"{summary['source_label_agreement']['agreement_rate']:.2%}"+'；源标签有噪声，不是准确率。')
        consistency=summary.get('consistency_first_pass') or {}
        st.write('固定十条重复运行的情感完全一致率：'+f"{consistency.get('sentiment_exact_agreement',0):.0%}"+'；这是稳定性检查。')
        st.write(f"实际批处理执行时间：{summary['batch_execution_wall_seconds']/60:.2f} 分钟；没有可用的纯人工对照时间。")
        st.write(f"新模型调用记录 tokens：{summary['new_total_tokens']:,}；估算不是实际账单。")
        st.write('独立人工准确率、独立人工 F1、人工提效比例：未验证，不填写数值。')
    st.subheader('当前交付口径')
    for limitation in summary['limitations']: st.write('• '+limitation)
