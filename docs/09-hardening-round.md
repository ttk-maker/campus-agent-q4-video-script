# 追加边缘与困难场景：事实边界、时长与检查版本

本轮从 2026-11-06 20:35（Asia/Shanghai）开始，按用户要求先复现困难输入，再修复并验证。

## 修复前失败与原因

新增 11 项测试在旧实现上出现 **8 failures**。[修复前输出](../examples/hardening/before.txt) 保留失败并脱敏路径；[修复后输出](../examples/hardening/after.txt) 为 11 项全部通过。

| 困难场景 | 原因 | 修复 |
| --- | --- | --- |
| `We are now here.` → `We are nowhere.` | 删除全部空白，丢失词边界 | 保留英文词间空格 |
| `支持字幕？` → `支持字幕。` | 删除问号，把疑问视为陈述 | 保留问号 |
| `不支持字幕，导出。` → `不支持，字幕导出。` | 删除句内标点，改变分句语义 | 保留句内标点 |
| `面积2m²。` → `面积2m2。` | NFKC 把单位上标兼容折叠 | 事实检查改用 NFC |
| 超长非一位小数时长 | Decimal 乘法先舍入 | 先精确比较量化值，拒绝无效输入 |
| 模型失败 / 步数用尽 | 最终 Trace 未完整持久化 | 结束事务写入模型错误及 stop 标记 |
| 旧 ready 缓存 | 检查 hash 不含算法版本 | hash 包含检查策略版本；旧结果归档到数据库 check_history，重新检查 |

事实匹配现在仅忽略汉字之间空白及有限句末陈述/感叹标点；保留英文词边界、内部标点、数字符号、问号和单位上标。检索、语速估算使用独立规范化方法，不共用事实等价语义。此策略依旧是保守原文比对，不能判断来源本身是否真实，也不能替代语义事实验证。

## 分层测试与示例

全量 [Python 报告](../examples/tests/report.json) **76 项通过**，包括真实双线程租约、多来源事实不能互借、旧策略复查及原有跨进程恢复。旧通过结果在 Agent 再次运行时重检；不修改已有脚本，历史检查在数据库归档。

[8 组 review 实际案例](../examples/hardening/review/report.json) 全部符合预期：英文边界、问句、分句、上标、数字小数、合法空白标点、1 秒不可满足、转场导致超时长。`review` 使用真实业务检查工具，但没有模型决策，也不会偷偷修改用户稿件；不合格稿返回 cannot_satisfy/未就绪，属于正确阻断。输入、输出、Trace 均在各案例目录。

[Chrome 回归](../examples/hardening/browser/report.json) **25 项通过**，包括手改无依据结论后阻断、用户允许继续后修正、修改时长重新检查、故障续跑、重复执行与刷新恢复。测试使用独立数据库。

## 复现与边界

```powershell
py -3.10 -m scripts.test_report
py -3.10 -m scripts.hardening_examples --output runtime/hardening
$env:MODEL_BASE_URL='http://localhost:11434/v1'
$env:MODEL_NAME='qwen2.5:7b-instruct'
py -3.10 -m scripts.hardening_examples --mode real --output runtime/hardening-real
```

CI 已加入离线困难案例。真实模型补测结果见下方追加记录；此前真实模型证据保持原样，使用当前工具重新核查成功稿，未声称重跑整个真实模型验收集。时长仍是启发式估算，最终配音与视频需要实测。


真实模型词边界案例：本机 qwen2.5:7b-instruct 7步完成，先观察28秒时长通过、事实检查失败，再把首镜头 We are nowhere. 修为来源原文 We are now here.，重新估算28秒并通过规则检查，最终版本v2。证据 [输入与实际运行](../examples/hardening/real/english_boundary/run.json)，未使用review或Mock代替模型。


真实1秒案例暴露反馈压缩问题：模型反复缩短停留，估算仍为4.5秒，但未及时停止。适配器原先只保留总时长，删掉了逐镜头voice_seconds。新增回归先复现缺字段（examples/hardening/before-voice-feedback.txt），修复后把实际最低朗读时间保留给模型，并提示停留低于旁白下限不会进一步变短；不得删事实词语或虚构更快语速。该反馈由真实估算工具产生，不是预写不能完成的模型答案。新增第12项hardening测试，全量75项。


第二次真实1秒复测仍耗尽16步（examples/hardening/real-duration-retest/），虽曾缩成单镜头1.5秒，仍反复缩短停留。因此增加工程可证明下限：估算工具遍历全部目录事实，按相同语速公式求最短完整事实旁白时间。仅在这个下限大于目标时标记proven_impossible；存在任何更短事实或空库时不作此判定。双检查完成且已证明当前资料无解时，动作空间仅保留finish，由真实模型返回cannot_satisfy并说明原因。不是宣称模型自行证明无解；这是事实原文组合策略下的执行守卫，真正有可行方案的修订仍由模型决定。界面同时显示最短事实所需秒数及补资料/调整时长建议。第13项hardening回归校验整个目录与空库边界，全量76项通过。检查策略升级为grounding-v2-boundaries-duration-v2，旧检查重新计算。最终真实复测单独留在real-duration-final，不覆盖前两次失败。


最终真实1秒案例：4步，先检索与估算，再规则检查，工具给出整个目录最短完整事实1.5秒>目标1秒，模型finish(cannot_satisfy)。脚本保持unverified，原因及0.5秒最低缺口可由catalog_bound复核。[实际输入/输出与Trace](../examples/hardening/real-duration-final/impossible_duration/run.json)。本轮题四本地验证至21:22，约47分钟（包含与题二交替推理与等待）；CI收尾计入总交付记录。
