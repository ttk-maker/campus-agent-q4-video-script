# 评估

本地63项Python测试与25项Chrome交互检查通过，见 [tests/report.json](../examples/tests/report.json)、[逐项输出](../examples/tests/unittest.txt)、[browser/report.json](../examples/browser/report.json)。离线8类场景共10次运行均通过，见 [mock/acceptance.json](../examples/mock/acceptance.json)。真实决策与离线检查分开记录。

## 验收映射

| 验收点 | 实际证据 | 说明 |
| --- | --- | --- |
| 正常生成 | [real/normal](../examples/real/normal/) | 无预设初稿，Qwen实际生成并完成当前版本双检查，时长10秒；重复运行0模型步 |
| 缺关键信息 | [mock/missing](../examples/mock/missing/) 与逐字段Python测试 | 缺输入是入口守卫，0模型调用，不把这条路径当模型决策证据 |
| 无素材 | [real/no_materials](../examples/real/no_materials/) 原失败、[修复复测](../examples/real-empty-retest/no_materials/) | 原16步耗尽但没有编造；复测2步明确needs_information，未生成脚本，历史原报告保持false |
| 工具失败 | [real/tool_failure](../examples/real/tool_failure/) | 实际检索失败一次，模型选择重试，最终10秒脚本双检查通过，第二次执行复用结果 |
| 超长修正 | [real/over_duration](../examples/real/over_duration/) | 给定已有38秒初稿，模型实际删去1个镜头并改为10+10，工具复估20秒；8动作内结束。初稿是测试输入，不假称模型首轮生成 |
| 无法满足时长 | [mock/too_short](../examples/mock/too_short/) | 1秒目标仍受旁白1.5秒下限约束，最终cannot_satisfy；无虚假通过 |
| 无依据产品结论 | [mock/claim_risk](../examples/mock/claim_risk/) 与 [real/claim_risk](../examples/real/claim_risk/) | 真实Qwen观察“效率提升80%”的规则失败，删去无依据结论后重新估算、检查，8步完成28秒稿；每句均有P01/F01支持 |
| 改写检索 | [mock/rewrite](../examples/mock/rewrite/) | 首次空查询后改“字幕”，检索结果转为found；真实空库分支单独实测 |
| 编辑前后状态 | HTTP测试与 [浏览器报告](../examples/browser/report.json) | 手动添加80%原文被保留并报错，不静默改写；随后显式让Agent修复 |

最终汇总由 `python -m scripts.verify_evidence` 读取实际输出、检查hash和逐镜头来源对齐重新核对，见 [acceptance.json](../examples/acceptance.json)。不把历史失败报告改为成功；该汇总明确引用复测目录。

## 首次失败与诊断

1. [real-initial-failure](../examples/real-initial-failure/)：仅要求JSON对象时，模型反复向无参数估算工具传整份scenes，并缺动作说明。16步后budget_exhausted，未完成、未标就绪。运行结果完整保留。
2. [real-schema-interrupted](../examples/real-schema-interrupted/)：加入JSON Schema后格式改善，但模型反复估算相同38秒草稿，没有检索与修订。观察到无进展后由开发者中止该诊断进程，保存当时SQLite状态及Trace；明确标记developer_interrupted，不假称自然终止或完成。
3. 增加按状态阶段开放工具及精简上下文，模型才完成真实38→20修订。选择/内容仍由模型输出，不由工程代码替模型填写秒数。
4. [real/no_materials](../examples/real/no_materials/)：模型先改写一次查询，随后不断重复空查询到16步上限。没有编造脚本，但未返回期望的待补资料终态。随后工具新增实际库存数量，把“整个库为空”与“查询未命中”分开，提示词要求空库结束请求资料，并针对该分支复测。完整历史报告仍保留false。

## 结论边界

JSON Schema与阶段骨架不代表模型已经理解所有场景。合法参数组合仍由工具再次判断，Trace可出现拒绝后恢复。正常案例只使用合成P01事实；单条事实导致脚本较简单，不能夸大为高质量广告创意。

核心事实策略是抽取式组合，不是开放式语义蕴含判断。它拒绝很多合理同义改写，换来可核验的安全边界。素材本身如果虚假，系统不会自动发现；品牌许可标题/画面规则也由资料提供者负责。

时长是基于字符和停留时间的启发式估算，不是真实音频。平台主要用于品牌适用性检查；受众作为模型输入，未独立评测受众适配效果。CI跑Python3.10/3.12与离线Chromium，真实Qwen只在本机验证。样本有限，不宣称生产成功率。

最终边界复核：比较事实时保留数字附近标点与正负号，新增1.0≠10、-5≠5、1-2≠12的反例测试。最终证据核查还用当前版本工具重新计算所有成功真实脚本的事实/时长，未重复调用模型，也不伪称重新运行整套推理。真实网页normal脚本10秒，运行中刷新恢复通过，见 [browser-real/report.json](../examples/browser-real/report.json)。
