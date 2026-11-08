"""Generate a review-gated Chinese Phase 4 PDF using ReportLab; never invent outcomes."""
from pathlib import Path
import json
import sqlite3
from contextlib import closing
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.pagesizes import A4


def generate_report(root):
    root = Path(root)
    evidence = json.loads((root / 'data/processed/phase4_business_evidence.json').read_text(encoding='utf-8'))
    approval = json.loads((root / 'data/processed/phase4_approved_strategies.json').read_text(encoding='utf-8'))
    proposal = json.loads((root / 'data/processed/phase4_strategy_review_proposal.json').read_text(encoding='utf-8'))
    if approval['evidence_id'] != evidence['evidence_id'] or len(approval['approved']) != 5:
        raise ValueError('Matching approved strategy snapshot required')
    approved_ids = {a['draft_id'] for a in approval['approved']}
    with closing(sqlite3.connect(root / 'data/processed/strategy_reviews.sqlite')) as db:
        current_ids = {r[0] for r in db.execute('SELECT draft_id FROM strategy_drafts WHERE status=?', ('approved',))}
    if not approved_ids.issubset(current_ids):
        raise ValueError('Approval snapshot is stale; an approved version was changed or revoked')
    if not all(s['draft_id'] in approved_ids for s in proposal['strategies']):
        raise ValueError('Unapproved content cannot enter the report')
    font_path = Path('C:/Windows/Fonts/simsun.ttc')
    if not font_path.is_file():
        raise FileNotFoundError('A CJK TrueType font is required for an embedded, portable Chinese PDF')
    pdfmetrics.registerFont(TTFont('STSong-Light', str(font_path), subfontIndex=0))
    blue = colors.HexColor('#164C72')
    body = ParagraphStyle('body', fontName='STSong-Light', fontSize=10.5, leading=17, spaceAfter=10, wordWrap='CJK')
    title = ParagraphStyle('title', parent=body, fontSize=24, leading=32, textColor=blue, spaceAfter=17)
    heading = ParagraphStyle('heading', parent=body, fontSize=15, leading=23, textColor=blue, spaceBefore=12)
    small = ParagraphStyle('small', parent=body, fontSize=8.5, leading=13, spaceAfter=7)
    story = []
    def p(text, style=body): return Paragraph(escape(text), style)
    def add(text, style=body): story.append(p(text, style))
    def table(rows, widths):
        t = Table([[p(str(c), small) for c in r] for r in rows], colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8F1F7')),
                              ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
                              ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),
                              ('BOTTOMPADDING',(0,0),(-1,-1),5),
                              ('LINEBELOW',(0,0),(-1,0),.6,blue),
                              ('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#D8E1E7'))]))
        story.extend([t, Spacer(1,12)])
    names = {'product_quality.color_fading':'褪色反馈','other.specific_other_issue':'其他具体问题',
             'product_description.image_mismatch':'图片与实物差异','delivery.delay':'物流慢反馈',
             'product_price.low_value':'价值感反馈','product_quality.material_quality':'面料问题','size_spec.length_mismatch':'长度不合适'}
    add('AI 电商消费者洞察', title)
    add('中文服饰样本分析与已批准核查计划', heading)
    add('第四阶段报告  |  2026-11-08  |  个人作品集原型', small)
    add('本报告将真实语料、模型提取、假设和人工批准分开记录。批准对象是后续原文核查计划，不代表评论标签已人工确认，也不代表整改已执行或经营效果已实现。')
    add('01  样本与主要线索', heading)
    add('从 Prompt 调试集按固定哈希另取二十条评论，排除先前定向冒烟评论及已识别联系方式记录。二十条均通过结构校验且纳入分析；模型标记十一条正向、八条负向、一条混合。独立测试集未进入本分析。')
    rows = [['模型标记问题','支持评论数','样本内占比','核查提示']]
    for i in evidence['issues']:
        rows.append([names[i['issue_label']],i['review_count'],f"{i['sample_share']:.0%}",i['priority_band']])
    table(rows,[130,75,80,210])
    add('统计单位为唯一评论文本，一条评论可对应多个问题；各问题占比不能相加作为人数。这里的占比是模型样本标记率，不是店铺差评率或平台投诉率。', small)
    story.append(PageBreak())
    add('02  优先级与证据口径', title)
    add('可用字段的启发式模型', heading)
    add('P = (7/13) F + (6/13) N。F 为某问题评论数除以本样本最多问题的评论数；N 为该问题中严格负向评论数除以该问题评论数，混合情绪另列。')
    add('原方案中的增长率 G 和消费者关注度 H 缺少日期、点赞或互动字段，因此不计算，也不填零。剩余原权重按比例归一化。支持数少于三条仅显示“样本不足，先人工核查”；这一门槛不是统计显著性检验。')
    add('权重敏感性与限制', heading)
    add('已比较 F 权重为 0.35、7/13 和 0.70 时的排序，保留并列。当前 N 有差异，但小样本下排序不能证明外部有效性；分数只辅助核查，不衡量经济损失、严重程度或预期收益。')
    add('事实、假设、计划', heading)
    table([['层级','可用内容','边界'],['样本记录','评论数量、模型问题标签、原文证据','模型标签尚未人工复核'],
           ['待验证假设','页面信息、材质、配送预期等可能原因','没有证据证明责任或因果'],
           ['已批准计划','S1-S5 的修订原文核查计划','尚未执行，不等于效果实现']], [75,205,215])
    add('每项诊断通过 fact_ids 引用 Python 生成的值与分母，并通过评论 ID 追踪证据。没有把模型自由生成的数字作为经营统计。', small)
    story.append(PageBreak())
    add('03  已批准的核查计划', title)
    add('审核人：项目用户（本聊天）。明确批准消息：“批准修订后的 S1—S5”。批准时间记录于本地审核账本，正文版本为 human-review-proposal-v1。', small)
    rows = [['编号 / 核查对象','当前可执行动作','建议环节','拟定周期']]
    for s in proposal['strategies']:
        rows.append([s['strategy_id']+' '+s['name']+'（'+str(s['support_reviews'])+'条）',
                     '逐条复核原文、记录判定和缺失资料'+('，拆分含混标签' if s['strategy_id']=='S2' else ''),
                     s['proposed']['owner_function'],str(s['proposed']['validation_days'])+'天'])
    table(rows,[135,190,90,80])
    add('统一验证指标', heading)
    add('原文人工复核完成率 = 已完成复核并记录结论的该类评论数 / 当前该类待复核评论总数，期望方向为提高。判为误标、无问题或资料缺失也可形成有效复核结论，不要求审核者认同模型。')
    add('周期为后续计划，不是已经发生的实验耗时。当前不具备商品或订单映射，不执行实物、页面、调价或物流整改。取得授权的对应关系及资料后，再对原模型提出的条件动作另行审核。')
    add('审核过程纠正了什么', heading)
    add('网页试跑曾将完成率配成降低或澄清方向；后续 API 运行又将问题确认比例用于效果方向。修订版统一改为核查完成率提高，防止将审核误标变化误读为消费者体验改善。原模型输出保留，修订内容单独生成哈希并批准。')
    story.append(PageBreak())
    add('04  验证记录与交付边界', title)
    table([['真实工作流','验证内容','记录'],['评论分析','二十条新增评论，四批请求','30,244 tokens'],
           ['经营诊断','真实 API，五项诊断','8,497 tokens'],['策略生成','真实 API，五项策略','11,236 tokens'],
           ['人工审核','修订 S1-S5，内容版本绑定','五条核查计划获批']], [100,270,125])
    add('以上 tokens 仅覆盖本阶段所列运行，共 49,977；不包含此前网页试跑与其他阶段调用。实际人民币费用尚未对账，Dify 价格字段显示零不等于免费。', small)
    add('复现与追踪', heading)
    add('三个工作流均有真实平台导出文件。诊断与策略导出各完成七项核对；API 响应、请求去重账本、审核事件和正文哈希存于本地。阶段验收文档记录运行 ID 和文件哈希。')
    add('数据来源与局限', heading)
    add('数据源为 ChineseNlpCorpus 的 online_shopping_10_cats 公开语料；原始平台、采集时间、抽样方法和数据许可尚未确认。仅作本地作品集原型，公开展示前应解决授权或替换数据。未展示原始评论全文或凭证。')
    add('没有真实商品、订单、价格、日期和履约字段，不能据此计算 GMV、转化率、价格带、增长率、实际物流延迟或经营损失。没有完成三百条人工金标准，不报告分类准确率、Macro-F1 或效率提升。')
    add('下一步', heading)
    add('第五阶段将把数据概览、评论证据、策略审核和报告导出接入 Streamlit。模型标记复核、独立测试及最终作品集评估仍需在后续阶段真实完成。')
    add('来源：https://github.com/SophonPlus/ChineseNlpCorpus', small)
    output = root / 'reports/generated_reports/phase4_consumer_insight_report.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#D8E1E7')); canvas.line(40,40,555,40)
        canvas.setFont('STSong-Light',8); canvas.setFillColor(colors.HexColor('#52616B'))
        canvas.drawString(40,27,'AI E-commerce Insight | 样本洞察与核查计划')
        canvas.drawRightString(555,27,str(doc.page))
    SimpleDocTemplate(str(output),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=45,bottomMargin=55,
                      title='中文服饰样本洞察与已批准核查计划',author='AI E-commerce Insight 项目').build(story,onFirstPage=footer,onLaterPages=footer)
    return output


def generate_workspace_report(root, workspace_id, evidence, approved):
    """Report only currently approved matching evidence; arbitrary workspaces stay isolated."""
    root = Path(root)
    if not approved or not all(d['body'].get('evidence_id') == evidence['evidence_id'] for d in approved):
        raise ValueError('Approved plans matching the evidence are required')
    with closing(sqlite3.connect(root / 'data/processed/strategy_reviews.sqlite')) as db:
        current = {rid: json.loads(body) for rid,body in db.execute('SELECT draft_id,body FROM strategy_drafts WHERE status=?',('approved',))}
    if any(d['draft_id'] not in current or current[d['draft_id']] != d['body'] for d in approved):
        raise ValueError('Approval is stale or content changed')
    import hashlib
    signature = hashlib.sha256(json.dumps([evidence,sorted(d['draft_id'] for d in approved)],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    output = root / 'reports/generated_reports' / ('workspace_' + signature + '.pdf')
    pdfmetrics.registerFont(TTFont('WorkspaceCJK','C:/Windows/Fonts/simsun.ttc',subfontIndex=0))
    style = ParagraphStyle('wsbody',fontName='WorkspaceCJK',fontSize=10.5,leading=17,spaceAfter=10,wordWrap='CJK')
    heading = ParagraphStyle('wsheading',parent=style,fontSize=18,leading=27,textColor=colors.HexColor('#176D86'),spaceAfter=16)
    story=[]
    def add(text,head=False): story.append(Paragraph(escape(text),heading if head else style))
    add('消费者样本洞察与核查计划',True)
    add('当前工作区报告 | 批准的是核查计划，不代表已经执行或产生经营效果。')
    add('样本口径',True)
    add(f"已分析记录 {evidence['requested_reviews']} 条；纳入分母 {evidence['validated_in_scope_known_sentiment_reviews']} 条；失败 {evidence['failed_items']} 条；范围或信息不足排除 {evidence['excluded_scope_or_unknown']} 条。")
    names = {'product_quality.color_fading':'褪色反馈','other.specific_other_issue':'其他具体问题',
             'product_description.image_mismatch':'图片与实物差异','delivery.delay':'物流慢反馈',
             'product_price.low_value':'价值感反馈','product_quality.material_quality':'面料问题','size_spec.length_mismatch':'长度不合适'}
    for issue in evidence['issues']:
        add(f"{names.get(issue['issue_label'],issue['issue_label'])}：模型标记 {issue['review_count']} 条，样本内占比 {issue['sample_share']:.1%}，优先级分数 {issue['priority_score']:.3f}，{issue['priority_band']}。")
    add('问题为多标签，不将其总数当作人数；模型标记仍待人工复核。P=(7/13)F+(6/13)N，缺少时间增长和关注度数据。分数只用于样本核查顺序。')
    add('证据版本：'+evidence['evidence_id'])
    story.append(PageBreak())
    for index,draft in enumerate(sorted(approved,key=lambda d:d['body']['strategy']['strategy_id'])):
        if index and index%2==0: story.append(PageBreak())
        strategy=draft['body']['strategy']
        add(strategy['strategy_id']+' | 已批准核查计划',True)
        for label,key in [('动作','action'),('负责环节','owner_function'),('验证指标','target_metric'),('验证设计','validation_design'),('风险护栏','guardrail')]:
            add(label+'：'+strategy[key])
        add(f"拟定周期：{strategy['validation_days']} 天；目标方向：{strategy['target_direction']}。周期是计划，不是已发生的实验耗时。")
        add('批准版本：'+draft['draft_id'])
        add('执行条件：只有取得实际商品、订单或页面资料后，才讨论相应整改；当前批准不证明模型判断正确。')
    story.append(PageBreak())
    add('数据与交付边界',True)
    for note in evidence['limitations']: add(note)
    add('来源：当前工作区导入的评论及真实工作流输出。上传数据的来源和使用权限由导入者核实；默认案例来自 ChineseNlpCorpus 公开语料，具体平台和许可仍待核验。')
    add('本报告只载入批准正文；后续撤销或修改审批后，应重新生成。未完成人工金标准，不报告准确率、效率提升或经营收益。')
    def footer(canvas,doc):
        canvas.setFont('WorkspaceCJK',8); canvas.setFillColor(colors.HexColor('#52616B'))
        canvas.drawString(45,27,'AI E-commerce Insight | 本地样本报告')
        canvas.drawRightString(550,27,str(doc.page))
    SimpleDocTemplate(str(output),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=44,bottomMargin=50,
                      title='消费者样本洞察与核查计划').build(story,onFirstPage=footer,onLaterPages=footer)
    return output


if __name__ == '__main__':
    print(generate_report(Path(__file__).resolve().parents[1]))
