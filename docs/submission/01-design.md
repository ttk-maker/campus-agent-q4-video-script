# 题目4 · 短视频脚本 Agent：设计说明

交付日期：2026-11-07（Asia/Shanghai）。提交题号：4。仓库：https://github.com/ttk-maker/campus-agent-q4-video-script。固定交付标签：`q4-submission-20261107`。配套文档：https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/docs/submission/02-delivery-and-acceptance.md 。

本文件供评审理解业务、动态决策、工程边界与实际证据。最终提交 SHA 由固定标签解析：`git rev-parse q4-submission-20261107^{commit}`；本地独立交付副本首页附最终完整 SHA。文档不把自身所属 commit 的 SHA 写入自身正文，以避免自引用改变 commit。

## 1. 用户、需求与范围

帮助创作者生成有事实依据、满足目标时长上限的可编辑短视频脚本。

- 输入：主题、受众、平台、目标时长、风格，产品事实素材与品牌规则。
- 输出：标题、分镜、旁白/字幕、逐镜头预计时长与总时长、素材/事实ID、风险和任务状态；脚本就绪与任务完成分别报告。
- 成功标准：覆盖题目全部必须验收点，至少两条不同工具观察后的真实模型决策路径；硬约束由程序复验，工具实际失败不得虚报成功。
- 范围：CLI 与本机 HTTP/Web 工作台均可运行。业务工具使用合成资料、本地函数和SQLite；真实模型使用Ollama `qwen2.5:7b-instruct`。Mock只验证流程，不证明真实决策能力。

## 2. 动作流与模型职责

检索素材 → 无结果时模型改写查询或请求资料 → 提交分镜 → 估算时长与检查规则 → 模型观察失败后删改脚本并复查，或说明无法满足 → 结束。

动作接口：`search_materials(query)`、`submit_script(title, scenes)`、`estimate_duration()`、`check_rules()`、`finish(outcome)`。

每轮模型输出一个动作、参数及简短决策依据；执行器校验后执行工具，将实际观察回传模型，再产生下一动作或结束。Trace保存步骤、工具参数、返回结果和后续动作，不收集模型内部思维过程。预设状态骨架限定合法动作，模型负责范围内的具体选择；最终状态以工具证据为准。

真实超长示例以38秒初稿为输入；模型观察检查后删去1个镜头，把剩余镜头改为10+10秒，实际工具复估20秒并通过规则。Mock生成28秒，二者严格分开。真实工具失败后模型重试；空库复测请求补充资料。1秒不可行场景由工具证明完整事实旁白下限1.5秒后，模型输出无法满足。

默认16个模型动作，可配置1–100；模型HTTP90秒，租约120秒；上限返回 `budget_exhausted`，当前脚本与实际检查保留。

## 3. 架构与可靠性

CLI/Web → Agent循环与模型适配器 → 确定性工具与守卫 → SQLite；工具观察返回模型，输出状态由实际持久结果构造。无需多Agent或生产Runtime。

每分镜含source_id、fact_id、voiceover、visual、seconds。旁白需匹配已检索事实原文，保留英文词边界、数字标点、问号和单位上标；标题/画面也检查品牌规则。版本/hash绑定脚本、请求、资料与检索状态，改稿清除旧检查。completed必须当前版本时长与规则均通过；同ID不同输入拒绝，重复完成任务复用。SQLite持久化脚本修订、检查、工具尝试，租约防并发。

Python 3.10+标准库承担CLI、HTTP、模型请求与测试，SQLite承担本地事务和持久化。未使用第三方Agent框架。选择原生实现是为了使状态、授权、失败与重试边界容易检查；代价是需要自行维护协议与持久化逻辑。Node.js/Playwright仅用于浏览器自动化，不是应用启动依赖。

Web只监听本机，包含同源/Host/会话令牌与请求大小守卫；这是本机演示边界，不是生产账号认证。完整执行Trace应及时导出；网页内存任务记录有限，业务结果仍持久化。

时长公式：旁白秒数=向上取到0.1秒（有效字符数/风格语速+0.5秒停顿）；镜头秒数=max（画面停留秒数，旁白秒数）；总时长=各镜头之和+转场。目标是上限，不要求填满。手工“检查我的修改”保留用户原文，建立新请求并用确定性工具复查，标记mode=review；只有显式“让Agent继续处理”才由所选生成模式修订。

## 4. 原型与前端

[可导入Figma的动作流与痛点SVG](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/docs/prototypes/script-flow.svg)。图稿已交付，本项目没有Figma在线文件。前端为桌面结果画布+参数侧栏，窄屏先输入后结果；显示设置即时变更主题色、明暗、字号、密度和动效，偏好按项目保存在本地浏览器。业务参数只更新预览，显式点击运行才调用Agent，已有结果不会随预览改写。设计参考Open Design Tweaks，代码按本项目业务独立实现。

[实时调参设计与验证](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/docs/11-live-tweaks.md)；[网页使用手册](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/docs/07-user-manual.md)。

## 5. 验收点与证据

| 验收点 | 实际证据 | 核对重点 |
|---|---|---|
| 正常生成 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real/normal) | 无预设初稿，模型生成10秒脚本，当前版本双检查通过 |
| 缺关键信息 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/mock/missing) | needs_information，入口守卫，不作为模型决策路径 |
| 无素材 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real-empty-retest/no_materials) | 真实复测2步needs_information，不捏造来源或脚本 |
| 工具失败 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real/tool_failure) | 检索失败一次后模型重试，最终10秒且双检查通过 |
| 超时长后修正 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real/over_duration) | 38秒输入初稿→实际模型修订20秒，8动作 |
| 时长无法满足 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/hardening/real-duration-final) | 1秒目标低于1.5秒完整事实下限，cannot_satisfy，未就绪 |
| 无依据结论 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real/claim_risk) | 删除无素材支持的80%结论，重新检查28秒稿 |
| 词边界事实修复 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/hardening/real/english_boundary) | now here与nowhere不可混同，真实7步修复28秒 |
| 重复执行 | [输入、输出与运行记录](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/examples/real/normal/run-2-output.json) | 复用当前检查通过结果，0模型动作 |

至少两条真实模型循环的直接入口：

- [实际超长修订](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/examples/real/over_duration/run-1-trace.jsonl)
- [工具失败恢复](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/examples/real/tool_failure/run-1-trace.jsonl)
- [无素材请求补充](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/examples/real-empty-retest/no_materials/run-1-trace.jsonl)

证据同时保存输入、实际输出、Trace；目录中的JSON/JSONL是实际运行记录，截图只是补充。缺输入的入口守卫和Mock不计作真实模型决策证明。

## 6. 测试、失败与改进

本次交付从Git源码归档解压到独立目录，重跑全量Python测试 **76项**、离线CLI与历史证据校验；结果见 [交付前检查](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/examples/submission/preflight.json)。历史前端回归：业务25项、展示35项、实时调参37项通过；最终文档提交还将执行GitHub CI。CI只运行工程/Mock验证，不声称在runner上运行真实Qwen。

仅JSON对象约束时出现错误参数与重复估算，加入JSON Schema及阶段工具范围后完成真实修订；空库增加实际库存反馈；困难验证强化英文词边界和数字/符号，加入严格可证明的时长不可行下限。历史首轮失败、开发者中止诊断、空库16步耗尽与1秒失败均保留，最终汇总明确引用复测。

原始失败：[examples/real-initial-failure/](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real-initial-failure)、[examples/real-schema-interrupted/](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real-schema-interrupted)、[examples/real/no_materials/](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/real/no_materials)、[examples/hardening/real-duration-retest/](https://github.com/ttk-maker/campus-agent-q4-video-script/tree/q4-submission-20261107/examples/hardening/real-duration-retest)。最新综合证据入口：[验收结果](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/examples/acceptance.json)。历史目录里保留false报告是审计事实，不应删除，也不能仅选旧报告推断最新复测结果。

本次是交付封装，未修改后端、模型或前端运行逻辑，未再次调用模型生成整套真实结果；真实决策记录来自先前实际执行，本次程序重新核对留存证据。

## 7. 已知限制与下一步

采用保守的事实原文组合，能拒绝“支持字幕”之外的“效率提升80%”，但也会拒绝合理同义改写，创意质量未独立评测。事实真实性取决于素材提供者。时长是字符/语速及停留时间的启发式估算，不是TTS实测；受众适配未单独评分。无真实视频生成、配音、发布或公网服务。

样本为小规模合成场景，不代表生产成功率。模型可能返回非法动作、反复尝试、超时或达到步数上限，系统须诚实报告未完成。下一步优先扩展真实资料和模型重复评估，再根据业务接入生产服务、身份权限与可观测性。

## 8. AI辅助、个人贡献和用时

用户实际贡献：提供题目、规则、验收要求，决定项目优先级、额外边缘测试和前端方向，提供参考模板。AI承担需求梳理、原型、代码、测试、实际模型试验、失败分析、文档与GitHub操作。没有把AI生成内容记为候选人独立编码，也没有虚构用户已手工验收的记录。详见 [AI使用记录](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/docs/04-ai-usage.md) 与 [复盘](https://github.com/ttk-maker/campus-agent-q4-video-script/blob/q4-submission-20261107/docs/05-retrospective.md)。

首次交付2026-11-06 17:07–17:50，约43分钟；题二/题四共同追加困难测试20:35–21:30，约55分钟（共同投入）。 三项目共同前端精简2026-11-06 22:25–22:41约16分钟；共同Tweaks改造23:43至11-07 00:01约18分钟。实际累计已超过官方建议3小时，应按实际报告；这些是开发会话跨度，包含AI、推理与CI等待，不等于候选人个人独立工作时长。此次封装自2026-11-07 15:28开始，结束与耗时附最终交付副本。
