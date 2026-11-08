# AI E-commerce Insight

中文服饰消费者洞察与运营核查原型。使用 Python、Dify 和 Streamlit，将评论问题、原文证据、诊断、人工审核与 PDF 报告串联。

这是个人作品集项目。当前真实开发验证使用 20 条评论，出现 7 类模型标记问题，形成 5 项经用户批准的核查计划；不代表已执行整改或取得经营效果。独立人工评估尚未完成，暂无实测 Accuracy/F1 或效率提升数字。

## 运行公开代码

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

打开 http://127.0.0.1:8501 。公开代码没有原始评论、私人运行数据和审批记录，默认显示空白工作区。可上传**你有权使用**的 UTF-8 CSV，列为 `review_text`；也支持 `cat,review`（只保留衣服）。上传与分析为本地工作区，只有明确点击模型调用才发送所选评论。

## Dify 接入

在 Dify 导入 `dify/review_analysis_workflow.yml`、`business_diagnosis_workflow.yml` 和 `strategy_generation_workflow.yml`，配置你自己的模型供应商并发布。复制 `.env.example` 为 `.env`，分别填写三个应用的 Service API Key。DeepSeek 模型密钥只填 Dify 供应商设置；不要提交到仓库。

每批评论 1—5 条。API 调用有本地请求账本，超时或状态不明时先核对 Dify 日志，不自动重放。平台及插件版本变化可能影响导入，需要核对节点配置。

## 功能

- 六个业务页面：数据总览、消费者洞察、问题与优先级、履约线索、策略中心、报告中心。
- 人工标注与评估入口：盲标、原文证据校验、主动计时、独立复核和测试答案冻结。
- 失败项保留；报告只收录当前有效批准版本，证据变化后旧报告失效。
- 问题多标签统计允许占比之和超过 100%；缺失 GMV、订单、商品与时间信息时不编造相关指标。

## 数据与评估

本地开发语料发布方为 [ChineseNlpCorpus](https://github.com/SophonPlus/ChineseNlpCorpus)。服饰原始记录 10,000 条，保守清洗后 9,909 条；按源标签平衡抽样预留 200 条开发集和 100 条独立测试集，源标签不当作人工真值。

源平台、采集时间和许可尚未确认，因此仓库不分发原始文本、标注任务、含评论的报告或运行产物。请自行确认数据使用权；公开复现可自行编写并明确标注示例。原项目 300 条待人工标签没有由模型代填。

`src/evaluation.py` 提供固定词表 Macro-F1、多标签 Micro/Macro-F1、完全匹配率及失败分母处理。运行 `python scripts/evaluate_heldout.py` 仅检查本地评估状态或评分，不自动调用付费 API；须先有固定人工标注任务和冻结答案。参见 [标注规范](docs/annotation_guide.md) 与 [第六阶段说明](docs/phase6_walkthrough.md)。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

单元测试使用人工编写的合成夹具，不访问真实独立测试正文，不发起付费模型调用。`scripts/verify_phase5_ui.py` 是完整本地开发案例的验收脚本，需要私人案例产物，公开空白工作区不使用这份脚本。

## 目录

`src/`：数据处理、契约调用、审核、报告和评估；`app/`：本地产品；`dify/`：实际导出与节点代码；`tests/`：回归验证；`docs/`：口径与操作说明。

项目使用 AI 辅助开发。求职展示应如实区分本人业务分析、人工审核、工具实现与尚未完成的评估；不能将模型 confidence 或结构校验通过率写成模型准确率。
