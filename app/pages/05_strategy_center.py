import copy
import streamlit as st
from app.ui import context,heading,run_action,NAMES

service,wid=context()
heading('策略中心','先追溯诊断依据，再编辑和审核核查计划。审核不代表已实施。')
evidence=service.get(wid,'evidence'); diagnosis=service.get(wid,'diagnosis')
a,b=st.columns(2)
with a:
    st.subheader('经营诊断')
    st.caption('引用当前样本中的统计与评论；可能原因始终是待验证假设。')
    if st.button('生成诊断（调用模型）',disabled=not evidence or not evidence.get('issues'),key='run_diagnosis'):
        run_action(service,wid,'diagnosis')
with b:
    st.subheader('核查策略')
    st.caption('以诊断为依据，生成负责环节、验证指标、周期与风险护栏。')
    if st.button('生成策略（调用模型）',disabled=not diagnosis,key='run_strategy'):
        run_action(service,wid,'strategy')
if diagnosis:
    with st.expander('查看当前诊断与引用'):
        for finding in diagnosis['findings']:
            st.write('**'+finding['finding_id']+' · '+NAMES.get(finding['issue_label'],finding['issue_label'])+'**')
            for fid in finding['fact_ids']:
                fact=evidence['facts'][fid]
                st.caption(f"{fid}：{fact['value']}，分母 {fact['denominator']}")
            st.write('下一步核查：'+finding['next_validation'])
            for cause in finding['possible_causes']: st.write('待验证假设：'+cause['hypothesis'])
drafts=service.drafts(wid)
if not drafts: st.info('暂无策略草稿。请先生成诊断，再生成策略。')
else:
    st.divider()
    status_filter=st.radio('策略状态',['当前版本','已批准','待审核','历史版本'],horizontal=True)
    matches=[d for d in drafts if (d['status']!='superseded' if status_filter=='当前版本' else d['status']=='approved' if status_filter=='已批准' else d['status'] in {'pending','changes_requested'} if status_filter=='待审核' else d['status']=='superseded')]
    st.caption(f'{len(matches)} 个版本；已批准仅表示计划获批，评论标签仍需独立复核。')
    if matches:
        mapping={d['draft_id']:d for d in matches}
        selected=st.selectbox('选择策略版本',list(mapping),format_func=lambda x: mapping[x]['body']['strategy']['strategy_id']+' · '+mapping[x]['status']+' · '+x[:8],key='draft_select_'+wid+'_'+status_filter)
        draft=mapping[selected]; strategy=draft['body']['strategy']
        st.write(strategy['action'])
        st.write('**负责环节：**'+strategy['owner_function'])
        st.write('**验证指标：**'+strategy['target_metric'])
        st.write(f"**计划周期：**{strategy['validation_days']} 天 · **目标方向：**{strategy['target_direction']}")
        st.write('**验证方法：**'+strategy['validation_design'])
        st.write('**护栏：**'+strategy['guardrail'])
        if '完成率' in strategy['target_metric'] and strategy['target_direction']!='increase':
            st.warning('完成率指标与目标方向可能不一致，请先编辑修正再审核。')
        with st.expander('证据引用与局限'):
            for fid in strategy['fact_ids']: st.write(fid+'：'+str(evidence['facts'].get(fid,{})))
            for note in strategy['limitations']: st.write('• '+note)
        if draft['status']!='superseded':
            with st.expander('编辑为新版本'):
                with st.form('edit_'+selected):
                    action=st.text_area('核查动作',strategy['action'],height=130)
                    metric=st.text_area('验证指标与分母',strategy['target_metric'])
                    design=st.text_area('验证方法',strategy['validation_design'])
                    guardrail=st.text_area('风险护栏',strategy['guardrail'])
                    owner=st.text_input('负责环节',strategy['owner_function'])
                    days=st.number_input('拟定周期（天）',7,90,int(strategy['validation_days']))
                    direction=st.selectbox('目标方向',['increase','decrease','clarify'],index=['increase','decrease','clarify'].index(strategy['target_direction']))
                    if st.form_submit_button('保存新版本（需重新审核）'):
                        if not all(t.strip() for t in [action,metric,design,guardrail,owner]):
                            st.error('动作、指标、验证方法、护栏和负责环节均需填写。')
                        else:
                            changed=copy.deepcopy(draft['body'])
                            changed['strategy'].update(action=action,target_metric=metric,validation_design=design,guardrail=guardrail,owner_function=owner,validation_days=int(days),target_direction=direction)
                            try:
                                service.review_store.save_draft(changed,supersedes=selected)
                                st.rerun()
                            except ValueError as error: st.error(str(error))
            with st.form('decision_'+selected):
                st.write('**记录审核决定**')
                decision=st.selectbox('审核结果',['请选择','批准核查计划','要求修改','驳回'])
                reviewer=st.text_input('审核人代号')
                note=st.text_area('审核依据与适用范围')
                if st.form_submit_button('保存审核决定'):
                    if decision=='请选择' or not reviewer.strip() or not note.strip():
                        st.error('请选择决定，并填写真实审核人代号和依据。')
                    elif decision=='批准核查计划' and '完成率' in strategy['target_metric'] and strategy['target_direction']!='increase':
                        st.error('请先修正完成率指标的方向，再批准该版本。')
                    else:
                        service.review_store.decide(selected,{'批准核查计划':'approved','要求修改':'changes_requested','驳回':'rejected'}[decision],reviewer,note)
                        st.rerun()
