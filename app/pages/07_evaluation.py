"""Human-only blind annotation. Does not display or query model predictions."""
import json
import time
from pathlib import Path
import streamlit as st
from src.evaluation import AnnotationStore
from src.review_analysis import contract

ROOT=Path(__file__).resolve().parents[2]
store=AnnotationStore(ROOT)
st.title('人工标注与评估')
if not all((ROOT/'data/sample'/name).exists() for name in ['annotation_prompt_dev.csv','annotation_heldout_test.csv']):
    st.info('公开代码包不包含原始评论或人工答案。请按 README 准备本地数据后生成固定标注任务。')
    st.stop()
st.caption('模型答案和源标签均隐藏。先开发集，再冻结独立测试；原有六个业务页面继续保留。')
split=st.selectbox('标注集合',['prompt_dev','heldout_test'],format_func=lambda x:'开发集 · 200 条' if x=='prompt_dev' else '独立测试 · 100 条')
stats=store.progress(split)
cols=st.columns(3)
cols[0].metric('待标注',stats['total']-stats['completed']); cols[1].metric('已保存',stats['completed']); cols[2].metric('已人工复核',stats['reviewed'])
st.info('当前不显示准确率或 F1；人工金标准和固定模型预测均齐备后才能计算。validated 只表示结构及证据校验通过。')
if split=='heldout_test':
    st.warning('独立测试只供人工标注。不要把这里的原文或答案发给 AI 调试 Prompt；请先完成开发集规则调整。')
tasks=store.tasks(split); records=store.records(split)
rid=st.selectbox('评论编号',[t['review_id'] for t in tasks],format_func=lambda i:f'{next(j+1 for j,t in enumerate(tasks) if t["review_id"]==i):03d} · {i[:12]} · '+('已复核' if records.get(i,{}).get('review_status')=='approved' else '已保存' if i in records else '待标注'))
task=next(t for t in tasks if t['review_id']==rid)
saved=records.get(rid,{})
if store.freeze_record(split):
    st.success('独立测试答案已冻结。')
    st.json(store.freeze_record(split))
    st.stop()
st.subheader('原始评论')
st.text(task['review_text'])
with st.expander('标注规则'):
    st.markdown((ROOT/'docs/annotation_guide.md').read_text(encoding='utf-8'))
token=split+rid
if st.session_state.get('annotation_task')!=token:
    st.session_state.annotation_task=token
    st.session_state.annotation_elapsed=0.0
    st.session_state.annotation_started=None

def stop_timer():
    if st.session_state.annotation_started is not None:
        st.session_state.annotation_elapsed+=time.monotonic()-st.session_state.annotation_started
        st.session_state.annotation_started=None

left,right=st.columns(2)
if left.button('开始 / 继续计时',key='annotation_start',disabled=st.session_state.annotation_started is not None):
    st.session_state.annotation_started=time.monotonic(); st.rerun()
if right.button('暂停计时',key='annotation_pause',disabled=st.session_state.annotation_started is None):
    stop_timer(); st.rerun()
st.caption('计时状态：'+('进行中' if st.session_state.annotation_started is not None else '暂停')+'。离开页面前请暂停；浏览器关闭、后台停留不能自动识别。此计时仅记录标注，不代表 AI 辅助效率实验。')
scope_options=['']+sorted(contract.SCOPES); sentiment_options=['']+sorted(contract.SENTIMENTS)
with st.form('annotation_'+token):
    actor=st.text_input('真实标注者代号',value=saved.get('annotator_id',''))
    scope=st.selectbox('业务范围',scope_options,index=scope_options.index(saved.get('scope_status','')))
    sentiment=st.selectbox('情感',sentiment_options,index=sentiment_options.index(saved.get('sentiment','')))
    labels=st.multiselect('负向具体问题；没有则留空',sorted(contract.ALLOWED_LABELS),default=saved.get('issue_labels',[]))
    evidence_text=st.text_area('问题证据 JSON（每个标签一条原文）',value=json.dumps(saved.get('evidence',[]),ensure_ascii=False,indent=2),height=150,help='格式：[{"label":"完整标签","quote":"原文连续片段"}]')
    need=st.text_input('用户需求（推测请注明；无则留空）',value=saved.get('user_need',''))
    notes=st.text_area('歧义与备注',value=saved.get('notes',''))
    submit=st.form_submit_button('保存人工标注')
if submit:
    stop_timer()
    try:
        seconds=saved.get('annotation_seconds',0)+st.session_state.annotation_elapsed
        store.save(split,rid,dict(annotator_id=actor,scope_status=scope,sentiment=sentiment,issue_labels=labels,
            evidence=json.loads(evidence_text),user_need=need,notes=notes,annotation_seconds=seconds))
        st.session_state.annotation_elapsed=0.0
        st.success('已保存。修改后需重新人工复核。'); st.rerun()
    except (ValueError,TypeError) as error:
        st.error(str(error))
if saved:
    with st.form('review_'+token):
        reviewer=st.text_input('真实复核者代号',value=saved.get('reviewer_id',''))
        confirmed=st.checkbox('我已对照原文复核范围、情感、标签和证据；单人复核不等于双人一致性检验')
        approve=st.form_submit_button('确认人工复核通过')
    if approve:
        if not confirmed:
            st.error('请先实际复核并勾选确认。')
        else:
            try:
                store.approve(split,rid,reviewer); st.rerun()
            except ValueError as error: st.error(str(error))
if split=='heldout_test':
    with st.expander('冻结 100 条测试答案'):
        actor=st.text_input('冻结操作人')
        confirm=st.checkbox('开发阶段已结束，后续不根据本测试结果反复调参')
        if st.button('冻结独立测试答案',disabled=not confirm):
            try:
                store.freeze(actor); st.rerun()
            except ValueError as error: st.error(str(error))
