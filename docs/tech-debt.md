# 技术债清单（只记不改，专门任务再清理）

## 1. 自转 GGUF 缺 added_tokens 元数据（2026-10-26 发现）

- **现象**：`llama_tokenize("<|im_end|>", add_special=true)` 返回 6 个字面 subword token（`<`、`|`、`im`、`_end`、`|`、`>`），而非特殊 token 151645。字符串式聊天模板全部退化。
- **根因**：训练机 `tools/llama_convert/gguf-py` 是老版本（vocab.py 时代），只从 `tokenizer_config.json` 的 `added_tokens_decoder` 读特殊 token；Qwen3 该字段为空，added tokens 全在 `tokenizer.json` 的 `added_tokens`（26 个）→ GGUF 丢失 `tokenizer.ggml.added_tokens` 键。
- **影响面**：所有自转 GGUF（orig/sft1/sft2 全系）。词表本身完整（151936、EOG 标志完好），**PPL 类评测不受影响**（语料无特殊 token）；生成类评测（15 题抽查、demo 对话）受模板退化影响。
- **引擎侧已缓解**：EngineCore 按 token ID 直拼 Qwen3 聊天格式（151644/151645 钉死），与正确模板分词逐 token 等价，见 EngineCore.swift chatTokens 注释。
- **待修（训练线，需用户拍板）**：用钉版 llama.cpp（b11857）自带的新 gguf-py 重转 f16 → 重新量化 → 生成类评测重跑。引擎侧 ID 拼接保留（对两种 GGUF 都成立，不依赖修复时间）。

## 2. 0.6B 工具调用遵循率（2026-10-26 已解决，SFT3B 达标）

- **历史现象**：SFT2 零 tool_call 发射（40 题全口头确认）；SFT3 首轮（system 注入+空块+占比）仍 0%。
- **最终根因**：SFTDataset 只对最后一条 assistant 算 loss，五段式 schedule 轨迹的 tool_call 段永远被掩码在 prompt 里，模型从未被要求输出工具调用（SFT3 首轮只把口头确认训练得更强）。
- **修复**：assemble_train.py sft3 profile 把带 system 的轨迹按 assistant 逐条切前缀样本（6,346 条 tool_call 样本 + 6,355 条确认样本），SFT3B 重训 2 epochs。
- **结果（SFT3B Q5_K_M，40 题）**：发射率 100%、schema 通过率 100%、端到端 0%（CLI TCC 环境限制，见 #3）；15 题通用生成评测 PASS 无遗忘。
- **遗留观察**：泛化题的日期映射偏弱（「周五晚上七点」→ 2021-05-06 等，模型不从真实日期推算星期）。属 0.6B 训练分布外能力，T4 iOS 确认弹窗可兜底；若影响可用性再议日期指令增强。

## 3. demo-cli 无 app bundle，EventKit TCC 拒绝（2026-10-26 T3 实测）

- **现象**：`requestFullAccessToEvents` 在 CLI 下返回拒绝（「日历访问被拒绝」），日历无法真写入。
- **根因**：SPM 可执行文件无 Info.plist/签名 bundle，TCC 不弹授权。
- **影响面**：仅 demo-cli 端到端验证降级；引擎闭环验证不受影响（工具执行/回填/续跑已实测）。
- **待修**：T4 iOS app 里真机验证（Info.plist 权限串 + 系统弹窗），demo-cli 不修。

## 4. 演示壳对话历史无截断，多轮后解码变慢（2026-11-03 真机实测）

- **现象**：真机连续对话十几轮后解码掉到 9.4 tok/s；跑分模式稳定 38-47（每轮 `history.removeAll()`，DemoChatView.swift:216）。
- **根因**：正常对话 history 只增不减（DemoChatView.swift:76），引擎每轮清 KV 后全量重发历史，上下文越长预填充/解码越慢；叠加连续推理热降频（同一轮 20 秒内 Q4_K_M 47.4→38.5、Q8_0 32.9→24.6 实测）。
- **影响面**：仅演示壳交互体验；评测口径不受影响（跑分每轮独立上下文）。
- **待修**：滚动窗口截断（保留最近 N 轮）+ 热状态提示；演示壳完善项，不阻塞评测。

## 5. 幻觉评测脚本未对齐 SFT17 训练模板（think-tags 缺失，2026-11-03 发现）

- **现象**：`scripts/eval_hallucination.sh` 注释称 SFT17 为 --no-think 训练所以不带 `--think-tags`；但 SFT17 实际以 `--no-think`（`enable_thinking=false`）训练，官方模板会在每个 assistant 回合头注入空思考块，推理侧必须同款注入才分布一致。
- **实证**：同一 1.7B SFT17 Q4_K_M、同一日程 prompt，demo-cli 不带 `--think-tags` 时模型复读 system 提示并裸奔生成；带 `--think-tags` 时输出干净、tool_call XML 完整（2026-11-03 Mac A/B）。
- **影响面**：已发布的幻觉率/工具调用指标可能是在模板不匹配配置下测得，数值需重跑校准；iOS 演示壳已改为 thinkTags: true。
- **待修**：评测脚本统一加 `--think-tags` 并复跑 README 指标（口径变更需同步更新公开数据）。

## 6. SFT 自动重试不续训 + 磁盘满后二次失败（2026-11-04 实测）

- **现象**：SFT19 首次训练到 690/690 保存 final 时训练机磁盘满（`No space left on device`），`run_sft19.sh` 自动第二次尝试未从 checkpoint 续训，而是从 0/690 重新开始；若不干预会在同一保存点再次失败。
- **根因**：`train_sft.py` 没有 `resume_from_checkpoint` 参数，`run_sft19.sh` 的第二轮只是去掉 `--overwrite`，Trainer 仍从头训练；同时 smoke 检查点每个约 31G，训练前未清理。
- **影响面**：浪费约 2.5h 双卡训练时间；不修复会让长训练反复在末尾失败。
- **待修**：给 `train_sft.py` 加 `--resume <checkpoint>` 并在重试分支传入最新 checkpoint；训练前自动清理/归档 `*-smoke`；训练机磁盘水位门禁（<10G 拒绝启动）。

## 7. llama-server 评测未注入空思考块，正确模型看起来像坏了（2026-11-06 已修）

- **现象**：SFT20c 工人 Q5_K_M 首次日期评测 emit 1/60，输出复读输入或聊天确认；原始 HF checkpoint 用 transformers 直接推理完全正确，一度怀疑量化损坏。
- **根因**：SFT 训练用 `--no-think`（模板 `enable_thinking=false` 时在每个 assistant 回合头注入空 `<think>\n\n</think>\n\n`）；llama-server 只加 `--jinja` 不会注入空块。SFT20c 对模板错配极敏感，SFT20/SFT20b 较鲁棒，掩盖了问题。
- **修复**：评测/服务统一加 `--chat-template-kwargs '{"enable_thinking": false}'`（或引擎侧按 `thinkTags` 手动拼空块）。补上后三版模型 8 题回归全部 8/8。
- **遗留**：所有新模型评测必须与训练模板开关逐项对齐；引擎侧 worker 模型 spec 需显式 `thinkTags: true`。

## 8. CAS 一期能力边界（2026-11-08 实测，二期再补）

- **化简不到「教科书答案」**：math.js `simplify` 只合并同类项，不能约分 `(x^2-9)/(x-3)`、不能因式分解、不认 `sin^2x+cos^2x=1`；`rationalize` 同样不约分。二期接 nerdamer 或自写多项式除法。
- **符号积分未接**：`integrate_indef` 直接返回「二期 nerdamer」错误；定积分是 Simpson 数值解（20000 段，结果标「数值解」）。
- **单方程求解**：`solve` 只支持单变量单方程（默认区间 [-100,100]），线性方程组需要模型先代入消元；极限完全不支持。
- **math.js 双副本**：CLI 的 `apps/demo-cli/.../Resources/` 与 iOS 的 `apps/ios-shell/Math/` 各存一份 math.js（634KB），升级时必须同步；后续可考虑脚本校验 sha256。
- **iOS 计算页未真机点按**：设备目标编译通过、bundle 资源加载已实测，但 UI 交互尚未真机走查。
- **验收口径**：56/56 的「纯计算子集」不含上述能力（不定积分 2、极限 2、最值/切线/二阶/参数 4、化简/因式/方程组/圆 5）；对外引用时不能写成「69 题全过」。

## 9. CAS 二期遗留（2026-11-09）

- **still 不能因式分解/约分**：`simplify` 仍只合并同类项；本期只补了 `sin²+cos²→1` 自定义规则和 `sin^2 x` 解析，其余归 nerdamer。极限见 §10（数值实现，不是符号）。
- **剩余 11 题**：不定积分、换元积分、最值、平均值、二阶导（只调一次）、参数方程、面积上下顺序、复合函数、等比数列、线性方程组、圆；对外只报 58/69，不能写成「69 题全过」。
- **提示词三处副本**：`MathEvalTool.swift` / `gen_math_eval_sft.py` / `eval_math_e2e.py` 必须逐字一致，改一处要同步三处并重生成数据。
- **两份 math.js**：CLI 与 iOS 各存一份；bridge 已同步，math.js 升级时仍需 sha256 校验。
- **评测脚本**：`score_math_eval.py` 的隐式乘法/LaTeX 兼容改动会同时影响历史分数，引用旧分数时注意口径。
- **数字兜底假阳（已修）**：答案块里没有可解析表达式时曾按数字兜底，会把「最大值为 f'(2)」的 2 当答案；
  现跳过函数名后括号内的数字，历史分数已用修复后判分重评（v7 58→57）。
- **提示词继续加长无效**：v6/v7 实测（面积负值、平均值 eval、f'' 连调、2^k 级数）均未超过 v5 的 58/69，system prompt 不再堆补丁。

## 10. limit 是数值实现，不是符号证明（2026-11-09）

- **能力边界**：`op=limit` 用 ε 逼近/大值采样 + 收敛判定；振荡函数可能误判，无穷远发散靠采样，不做符号推导。
- **调用约定**：limit 复用 `lower` 作趋近点（`inf/-inf/数值`），不是独立参数；提示词三处副本必须同步。
- **误用风险**：v5 在「闭区间最值」题上把 limit 当成解最值工具；后续若补最值训练，需显式区分 derivative/solve 与 limit。
