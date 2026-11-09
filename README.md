# AI E-commerce Insight

中文服饰消费者洞察与运营核查原型。使用 Python、Dify 和 Streamlit，将评论问题、原文证据、诊断、人工审核与 PDF 报告串联。

这是个人作品集项目。已完成 300 条 AI 标注：首次 292 条通过结构和原文引用校验，8 条经 Codex AI 补充；281 条进入问题统计，出现 25 类模型标记问题。原 20 条案例及其 5 项用户批准计划独立保留，300 条研究的新策略仍为待审核。没有已执行整改或经营效果证据。

用户选择 AI 代标后，原保留样本进入 AI 研究，不再称为独立人工金标准测试。97.33% 是契约通过率，不是准确率；没有独立人工 Accuracy/F1 或人工提效比例。最终说明见 [AI 代标交付](docs/phase6_final_delivery.md)，简历版本见 [简历与面试讲述](docs/resume_project_final.md)。

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
- 标注与评估入口：AI 结果与人工存档分开，保留首次失败、补充来源和真实用户审核记录；已进入 AI 研究的样本不能冻结为独立人工测试。
- 演示模式隐藏评论正文与逐条引用，便于讲解产品而不展示来源许可未确认的原文。
- 失败项保留；报告只收录当前有效批准版本，证据变化后旧报告失效。
- 问题多标签统计允许占比之和超过 100%；缺失 GMV、订单、商品与时间信息时不编造相关指标。

## 数据与评估

本地开发语料发布方为 [ChineseNlpCorpus](https://github.com/SophonPlus/ChineseNlpCorpus)。服饰原始记录 10,000 条，保守清洗后 9,909 条；按源标签平衡抽样预留 200 条开发集和 100 条独立测试集，源标签不当作人工真值。

源平台、采集时间和许可尚未确认，因此仓库不分发原始文本、标注任务、含评论的报告或逐条运行产物。请自行确认数据使用权；公开复现可自行编写并明确标注示例。当前 300 条由 AI 完成，不称为人工真值。

`src/evaluation.py` 保留固定词表评分能力，但当前 AI 研究不生成独立人工质量数字。`src/ai_annotation.py` 计算弱标签一致性、重复稳定性与覆盖率。运行 `python scripts/evaluate_heldout.py` 仅检查状态；AI 研究样本会返回不适用，不会自动调用付费 API。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

单元测试使用人工编写的合成夹具，不访问真实独立测试正文，不发起付费模型调用。`scripts/verify_phase5_ui.py` 是完整本地开发案例的验收脚本，需要私人案例产物，公开空白工作区不使用这份脚本。

## 目录

`src/`：数据处理、契约调用、审核、报告和评估；`app/`：本地产品；`dify/`：实际导出与节点代码；`tests/`：回归验证；`docs/`：口径与操作说明。

项目使用 AI 辅助开发。求职展示应如实区分本人业务分析、人工审核、工具实现与尚未完成的评估；不能将模型 confidence 或结构校验通过率写成模型准确率。
