from pathlib import Path
import hashlib
import streamlit as st
from app.ui import context,heading,ROOT
from src.report_generator import generate_workspace_report

service,wid=context()
heading('报告中心','只将当前已批准的核查计划纳入报告，保留样本口径与数据局限。')
evidence=service.get(wid,'evidence')
approved=[d for d in service.drafts(wid) if d['status']=='approved']
st.metric('可纳入当前报告的计划',len(approved))
st.caption('模型标记不等于人工真值；批准计划不代表已执行或已取得经营效果。')
if not approved: st.info('当前没有已批准的计划。请在策略中心完成审核后再生成报告。')
if st.button('生成当前工作区 PDF',disabled=not evidence or not approved,type='primary'):
    try:
        path=generate_workspace_report(ROOT,wid,evidence,approved)
        service.put(wid,'report',{'path':str(path),'evidence_id':evidence['evidence_id'],
                                'approved_ids':sorted(d['draft_id'] for d in approved),
                                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        st.success('已生成，未调用模型。')
    except Exception:
        st.error('报告生成未完成，请检查当前批准版本、字体或本地文件。')
report=service.get(wid,'report')
if report:
    valid=bool(evidence and report['evidence_id']==evidence['evidence_id'] and report['approved_ids']==sorted(d['draft_id'] for d in approved))
    path=Path(report['path'])
    valid=valid and path.is_file() and path.resolve().is_relative_to((ROOT/'reports/generated_reports').resolve())
    if valid and hashlib.sha256(path.read_bytes()).hexdigest()==report['sha256']:
        st.download_button('下载当前核查报告',path.read_bytes(),'consumer_insight_report.pdf','application/pdf')
    else: st.warning('证据或批准状态已变化，旧报告不再作为当前有效报告提供下载。请重新生成。')
with st.expander('第四阶段历史报告'):
    st.caption('固定案例快照，不代表当前上传数据或最新审核状态。')
    history=ROOT/'reports/generated_reports/phase4_consumer_insight_report.pdf'
    if history.exists(): st.download_button('下载历史案例报告',history.read_bytes(),'phase4_case_study.pdf','application/pdf')
