"""Run: python -m streamlit run app/streamlit_app.py"""
from pathlib import Path
import os
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pandas as pd
import streamlit as st
from src.app_service import AppService, parse_upload
from src.workflow_runner import load_env

st.set_page_config(page_title='服饰消费者洞察', page_icon='◈', layout='wide')
st.markdown('''<style>
.block-container{padding-top:2.3rem;max-width:1450px}h1{letter-spacing:-.035em}h2{font-size:1.45rem!important}
[data-testid="stMetric"]{background:white;border:1px solid #DFE7EF;border-radius:12px;padding:18px}
[data-testid="stSidebar"]{border-right:1px solid #DCE5EE}div.stButton>button{border-radius:8px}
</style>''',unsafe_allow_html=True)
service = AppService(ROOT)
seed = service.seed()
if 'workspace_id' not in st.session_state:
    st.session_state.workspace_id = seed
pages = [st.Page('pages/01_dashboard.py',title='数据总览',icon='📊',default=True),
         st.Page('pages/02_consumer_insight.py',title='消费者洞察',icon='💬'),
         st.Page('pages/03_product_analysis.py',title='问题与优先级',icon='🔎'),
         st.Page('pages/04_delivery_analysis.py',title='履约线索',icon='🚚'),
         st.Page('pages/05_strategy_center.py',title='策略中心',icon='🧭'),
         st.Page('pages/06_report_center.py',title='报告中心',icon='📄'),
         st.Page('pages/07_evaluation.py',title='人工标注与评估',icon='📝')]
page = st.navigation(pages)
with st.sidebar:
    st.header('消费者洞察工作台')
    spaces = service.workspaces()
    options = [w['id'] for w in spaces]
    names = {w['id']:w['name'] for w in spaces}
    chosen = st.selectbox('当前工作区',options,index=options.index(st.session_state.workspace_id),format_func=lambda x:names[x],key='workspace_picker')
    if chosen != st.session_state.workspace_id:
        st.session_state.workspace_id = chosen
        st.rerun()
    with st.expander('上传服饰评论 CSV'):
        st.caption('UTF-8；列 review_text，或原始 cat、review。每个文件独立保存，不会覆盖案例。')
        uploaded = st.file_uploader('选择 CSV',type=['csv'],key='upload_csv')
        name = st.text_input('工作区名称',value='我的服饰评论')
        if st.button('检查并导入',disabled=uploaded is None,key='import_csv'):
            try:
                manifest_path=ROOT/'data/processed/split_manifest_private.csv'
                protected=set()
                if manifest_path.exists():
                    manifest = pd.read_csv(manifest_path,usecols=['review_id','split'])
                    protected = set(manifest.loc[manifest['split'].eq('heldout_test'),'review_id'])
                reviews, meta = parse_upload(uploaded.getvalue(),protected)
                st.session_state.workspace_id = service.create(name or '上传评论',reviews,meta)
                st.session_state.pop('workspace_picker',None)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    load_env(ROOT)
    with st.expander('工作流连接'):
        for label,key in [('评论分析','DIFY_API_KEY'),('经营诊断','DIFY_DIAGNOSIS_API_KEY'),('策略生成','DIFY_STRATEGY_API_KEY')]:
            value = os.environ.get(key,'')
            valid = bool(value and value.isascii() and not any(c.isspace() for c in value))
            st.write(label+' · '+('本地已配置' if valid else '待配置'))
        st.caption('密钥只从服务端环境读取，页面不显示或收集密钥。')
    st.divider()
    st.caption('本地原型 · 中文服饰场景\n\n模型标记待复核；已批准计划不代表已执行。')
page.run()
