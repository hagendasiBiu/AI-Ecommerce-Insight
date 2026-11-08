# 中文服饰评论标注规范 v1

## 目的和抽样

准备 300 条待人工标注评论，200 条用于规则与 Prompt 调试，100 条作独立测试。按源正负标签分层，各集合内部正负各半，不代表平台真实情感分布。原标签有冲突和明显可疑案例，不能作为最终评估真值。

`data/sample/annotation_prompt_dev.csv` 和 `annotation_heldout_test.csv` 中隐藏源标签，不填模型预测。开发者在调试时不阅读独立测试正文。人工先完成标签，再冻结测试答案；第三阶段调试只能使用开发池。若修改标注规则影响测试标准，需要记录版本并在不查看模型结果的条件下重标，不通过反复看测试结果调参。

本阶段只是准备任务，全部 annotation_status=pending。AI 不能代替人工完成金标准后自评。用户可在后续阶段分批标注，暂不要求现在填完。

## 填写顺序

1. `scope_status`：`in_scope`（服饰及其配送售后）、`out_of_scope`（明确其他业务）、`uncertain`（无法判断）。泛指“商品”“宝贝”的短评通常是 uncertain，不能臆造商品信息。是否纳入正式评估需在模型评估前按固定规则决定并报告分母。
2. `sentiment`：positive / neutral / negative / mixed / unknown。正负并存且都有实质表达为 mixed；信息不足为 unknown；仅客观描述、没有倾向为 neutral。不能把“不掉色”判成掉色抱怨。
3. `issue_labels_json`：JSON 数组，支持多个问题标签；只记录抱怨或明确未满足的需求。只有正向反馈或没有具体问题时填 `[]`，不能用 other 填补所有正评。
4. `evidence_json`：JSON 数组，与问题标签一一对应，每项为 `{"label":"标签", "quote":"原文片段"}`。quote 必须逐字出现在提供的 review_text 中，不能改写，不能恢复屏蔽的联系方式。
5. `user_need`：有明确需求时简短记录；仅为合理推测时写“推测：…”，不足以判断时留空。评价不等于用户购买意图或实际退货事实。
6. `annotator_id` 填真实标注者代号，`annotation_seconds` 记录真实主动标注耗时，不预填；`notes` 记录歧义。
7. 初次完成将 `annotation_status` 改为 completed；复核者填写 `reviewer_id` 和 `review_status`（approved / revise / rejected）。不可在未复核时填 approved。只有一位标注者时如实记录，不能声称双人标注一致率。

## 多标签词表

一级类通过标签前缀映射，实际类别键可由此派生；单个 primary_category 字符串不能承载多标签。

| 一级类别 | 允许的问题标签 |
|---|---|
| product_quality 商品质量 | material_quality、workmanship、damage、durability、color_fading、pilling |
| product_description 商品描述 | image_mismatch、spec_mismatch、missing_information |
| product_price 商品价格 | high_price、low_value、price_change |
| size_spec 尺寸规格 | too_small、too_large、length_mismatch、size_inconsistency |
| delivery 物流配送 | delay、packaging_damage、tracking_issue、wrong_or_missing_item |
| after_sales 售后 | refund_difficulty、return_exchange、slow_response |
| product_function 商品功能 | function_failure、performance_gap |
| shopping_experience 购买体验 | ordering_issue、communication_issue |
| other 其他 | specific_other_issue |

填完整键，例如 `product_quality.workmanship`。服饰版允许的叶子标签全部记录于上表，不在词表内的问题先标 specific_other_issue 并在 notes 解释。只有“很差”而无具体方面时，sentiment 可为 negative，issue_labels_json 仍可为 `[]`。无法分类不等于发现了“其他问题”。

## 边界处理

- 提到快递很快是正向配送反馈，不标 delivery.delay。
- 表示打算退货不等于已经退货，更不等于退款困难。
- 图片颜色和实物不同可标 image_mismatch；洗涤后褪色标 color_fading，二者不能互换。
- 尺码过大与描述尺码表错误可以共存，但后者必须有原文支持。
- 同一标签只标一次，证据取最短且足够支持判断的连续片段。
- 疑似品类错误和隐私标记只是待审提示，不是答案。

以上为规则说明，没有填写任何真实测试结果。第三阶段需要结构化校验器验证键、枚举、证据和审核状态；第六阶段再计算单标签情绪 Macro-F1、多标签问题 Precision/Recall/F1 等，不把自由文本需求直接当作分类准确率。
