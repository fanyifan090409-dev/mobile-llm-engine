# 数学 CAS 工具接入（2026-11-08）

> 决策：数学端采用「产品侧 CAS 工具」，模型负责理解题意/列式/讲解，工具负责精确计算。
> 背景：69 题客观集 SFT19 最好 45/69（65.2%），继续堆合成数据无效（SFT22 30、SFT23 38）。

## 一、CAS 是什么（一句话）

CAS（Computer Algebra System，计算机代数系统）= 会做符号推导的计算器。
普通计算器只给数值（1/3 → 0.3333），CAS 保留精确形式并能做代数操作：

- `1/3 + 1/6` → `1/2`（不是 0.5 的近似）
- `d/dx (x^2 + 3x)` → `2x + 3`
- `∫ 3x^2 dx` → `x^3 + C`
- `solve(x^2 - 5x + 6 = 0)` → `x = 2, 3`
- `simplify((x^2-1)/(x-1))` → `x + 1`

我们手机端用的是 JS 版 CAS（math.js / nerdamer），离线、毫秒级、1MB 以内。

## 二、选型

| 库 | 体积（min / gzip） | 覆盖 | 结论 |
|---|---|---|---|
| math.js | 729KB / 197KB | 表达式、分数、求导、化简、矩阵、统计 | 一期 |
| nerdamer | 536KB / 151KB | 符号积分、解方程、化简 | 二期按需 |
| Algebrite | 334KB / 79KB | 积分、求根、化简 | 备选（更新慢） |
| Pyodide+SymPy | 核心 12MB+ | 最全 | 不做默认 |

## 三、架构与接口契约

引擎层不改：`LocalTool` 协议已够用（`ToolSpec` + `execute`）。
CAS 工具放应用层（iOS/CLI），用 JavaScriptCore 加载打包进 App 的 math.js。

工具定义：

```json
{
  "name": "math_eval",
  "description": "精确计算数学表达式。适合求值、求导、化简、定积分、解方程、统计。输入必须是结构化表达式，不能是自然语言。",
  "parameters": [
    {"name": "op", "type": "string", "required": true,
     "description": "eval | derivative | simplify | integrate_def | integrate_indef | solve | stats"},
    {"name": "expr", "type": "string", "required": false, "description": "表达式，如 x^2+3*x；stats 时可省略"},
    {"name": "variable", "type": "string", "required": false, "description": "自变量，默认 x"},
    {"name": "lower", "type": "string", "required": false, "description": "定积分下限/解方程区间下限，可写 pi/2"},
    {"name": "upper", "type": "string", "required": false, "description": "定积分上限/解方程区间上限"},
    {"name": "stat_op", "type": "string", "required": false,
     "description": "mean | median | variance | std | variance_pop | std_pop | iqr | sum | min | max | combination | permutation | binomial | regression"},
    {"name": "data", "type": "string", "required": false, "description": "统计用逗号分隔数据；regression 用 x1,y1;x2,y2"}
  ]
}
```

返回给模型（ToolLoop 的 `.result` 风格；engine 内部还带 `latex`/`numeric`/`ms`，给 UI 用）：

```json
{"status":"ok","result":"3 * x ^ 2 + 2"}
```

失败：`{"status":"error","result":"无法解析表达式：…"}`，模型据此改写后重试，最多 2 次。

## 四、分两期落地

### 一期：独立计算模式（不训练模型，立刻可用）

- iOS 壳/CLI 增加「计算」入口：用户输入表达式或拍题转文字后，走 CAS 精确计算；
- 纯数学输入可用正则直接路由（含 `= ∫ d/dx solve` 等关键词），不依赖模型判断；
- UI 必须回显「我理解的表达式」，用户可改，避免模型/解析错误被藏起来；
- 验收：69 题里的纯计算子集（求值/求导/定积分/统计）工具路径 ≥95%，P95 <300ms。

### 二期：模型工具调用（需要小轮 SFT）

- 新增 1,000 条 `math_eval` 调用样本：中文题 → `{"op":…,"expr":…}` → 工具结果 → 中文讲解；
- 起点 SFT21b（行为最好）或 SFT19（学术最好），带 1,000 条工具调用回放 + 700 条学术回放；
- 目的：模型自己判断什么时候该调工具，而不是让用户手动切模式；
- 验收：工具调用成功率 ≥90%；69 题端到端 ≥80%；工具调用 40/40、日期 58/60 不回退。

## 五、边界与风险

- **不解决「读不懂题」**：应用题列式错了，CAS 只会把错误表达式算得很准；所以必须回显表达式让用户确认。
- **表达式注入**：只用 math.js 的表达式解析器，不用 `eval`/`Function`；不加载远程 JS。
- **超时与内存**：单次 2s 上限；JavaScriptCore 懒加载，不拖慢首屏。
- **符号积分**：math.js 不覆盖，二期再接 nerdamer；一期定积分先用数值积分，结果标注「数值解」。
- **化简能力有限**（实测）：math.js `simplify` 只合并同类项，不能约分 `(x^2-9)/(x-3)`、不能因式分解、不认 `sin^2+cos^2=1`；这些归二期 nerdamer。
- **没有极限/方程组/二阶导开关**：极限、线性方程组、最大值应用题、参数方程求导需要模型列式或多次调用，CAS 单次不包办。
- **解方程**：只支持单变量单方程，区间默认 [-100,100]；网格 4000 点 + 二分，结果标「数值解」。
- **证明题/FRQ 讲解**：仍归模型，CAS 只保证中间计算。

## 六、回滚

- 一期完全独立入口，不改模型、不改引擎；关掉入口即回滚。
- 二期模型单独存 `sft25-cas`，不达标就保留 SFT21b/SFT19，不替换模型池。

## 七、一期实现状态（2026-11-08）

代码（应用层，未动 EngineKit）：

- `apps/demo-cli/Sources/demo-cli/Resources/math.js`：math.js 15.2.0 浏览器构建（634KB，Apache-2.0，许可证同目录）；
- `Resources/MathEvalBridge.js`：`__casEval` 桥接（精确分数、变量改名避开 math.js 的 `t`=吨单位、Simpson 定积分、数值求根、统计）；
- `MathEvalEngine.swift`：JavaScriptCore 懒加载 + 串行锁 + 表达式长度上限；暴露 result/latex/numeric/ms；
- `MathEvalTool.swift`：`math_eval` LocalTool（`.result` 回填，二期训练契约的 usagePrompt 已就位）；
- `CalcRouter.swift` / `CalcCLI.swift`：正则路由（`d/dx`、`积分…从…到…`、`解方程`、`均值:` 等）+ 显式 flags；
- `CalcSelfTest.swift`：读 `calc_acceptance.json` 跑验收；
- `train/eval/gen_calc_acceptance.py`：从 69 题生成纯计算子集验收数据。

CLI：

```bash
cd apps/demo-cli
swift build
.build/debug/demo-cli --calc "1/3+1/6"                 # = 1/2
.build/debug/demo-cli --calc "d/dx x^3+2*x"            # = 3 * x ^ 2 + 2
.build/debug/demo-cli --calc "积分 x^2 从 0 到 1"       # = 1/3（数值解）
.build/debug/demo-cli --calc "解方程 x^2-5x+6=0"       # = 2, 3（数值解）
.build/debug/demo-cli --calc "均值: 4,8,6,10,2"        # = 6（数值解）
.build/debug/demo-cli --calc-repl                      # 交互计算
.build/debug/demo-cli --calc-selftest                  # 一期验收
.build/debug/demo-cli --model <gguf> --math            # 实验：注册 math_eval（模型未训练，可能瞎调）
```

验收结果（Mac M5，debug/release 均同）：

- 纯计算子集 **56/56（100%）**：ap_calc 17、precalc 20、ap_stats 19；路由回归 16/16；
- P95 **97-100ms**、最慢约 220ms（Simpson 20000 段定积分）、math.js 首次载入 40-77ms；
- 排除 13 题：不定积分 2、极限 2、最值/切线/二阶/参数方程 4、化简/因式分解/方程组/圆 5 —— 需要推导或二期能力；
- 已修回归：负整数符号（mathjs Fraction 的 `n` 无符号）、隐式乘法 `5x` 变量漏替换、`\cdotx` 非法 LaTeX。

iOS 入口（2026-11-08 补）：

- `apps/ios-shell/Sources/MathCalcView.swift`：输入框 + 示例 + 结果卡（回显「我理解的计算」+ 数值解标记 + LaTeX 折叠）；计算不需要模型；
- 入口两处：对话页快捷芯片「计算」（模型未加载也常驻）、设置 → 更多 → 数学计算；
- `MathEvalEngine.swift` / `CalcRouter.swift` 由 iOS 工程以相对路径直接引用 CLI 的同一份源码（`MathEvalEngine` 用 `#if SWIFT_PACKAGE` 区分 `Bundle.module` / `Bundle.main`）；
- 资源：`apps/ios-shell/Math/` 以文件夹引用打进 App（`Math/math.js`），加载时 `subdirectory: "Math"`；
- 验证：真机目标 `xcodebuild` 通过；用 `Bundle(path: EngineShell.app)` + `subdirectory: "Math"` 的 macOS 小程序实测 1/2、3x²+2、解方程均正确。

未做（后续）：

- 二期 1,000 条 `math_eval` 工具调用 SFT 与 69 题端到端验收；
- iOS 计算页的真机点按走查（设备目标已编译通过，资源加载已实测）；
- `apps/ios-shell/Math/` 与 `apps/demo-cli/.../Resources/` 是两份 math.js 副本，升级 math.js 时必须同步。

## 八、二期实现状态（2026-11-09）

数据（`train/synthesize/gen_math_eval_sft.py` + `gen_math_eval_multistep.py`）：

- 单步 1,853 题 / 3,706 行：eval 448（应用题、反函数、复合、余数、级数、距离、行列式、复数模）、derivative 334（含反三角）、
  stats 360（normalcdf / 二项式系数 / 二项方差）、area 85、integrate 180、solve 150、simplify 100、word 196；
- 多步 190 条轨迹 / 570 行：驻点、切线、二阶导、区间平均值、复合函数；
- 生成器 `add()` 对 69 题原题做全局拦截，二次核对污染 0；
- 提示词三处逐字同步：`MathEvalTool.swift` / `gen_math_eval_sft.py` / `eval_math_e2e.py`（v7b，最终采用版）。

训练（LoRA r16；v1-v3 从 SFT19 final 起 3 epochs，v4 从 v3 final 续训 2 epochs）：

| 版本 | 数据 | 69 题端到端 | 备注 |
|---|---|---|---|
| SFT27 | v1 1,069 题 | 47/69（68.1%） | emit 66/69 |
| SFT27b | v2 1,448 题 | 48/69（69.6%） | emit 69/69 |
| SFT27c | v3 1,745 题 | 54/69（78.3%） | ap_stats 19/19 |
| SFT27d | v4 1,853 题 | 初评 53/69；补 CAS + 提示词后 **58/69（84.1%）** | 前一版 |
| SFT27e | v4 + 28 条 limit | **58/69（84.1%）**，极限题通过 | 采用 |
| SFT27f | v6（v7c 提示词 + 定向补量 1,977 行） | 55/69（79.7%） | 不采用 |
| SFT27g | v7（从 v5 续训修复集 1,977 行） | 58→57/69（82.6%，修判分后） | 不采用 |

评测口径：Q5_K_M、temp 0、模型自行调 `math_eval`、真实 CAS 回填、最多 3 轮。

- **58/69（84.1%）**：ap_calc 18/25、precalc 21/25、ap_stats 19/19；emit **69/69（100%）**，满足 ≥80% / ≥90%；
- 剩余 11 题：不定积分、换元积分、最值、平均值、二阶导数（模型只调一次）、参数方程、面积上下顺序、复合函数、
  等比数列、线性方程组、圆；其中 7 题超 CAS 单次能力，4 题属模型列式/多步问题；
- 40/40 工具与 58/60 日期属既有 0.6B 工人模型验收，本次未改工人模型；CAS 模型独立存放，不替换模型池。
  SFT27e Q5/Q4 在训练机 `tools/llama_convert/sft27e_cas_gguf/`。

本期关键修复：

- LaTeX 反三角与省括号函数归一（`\arctan x`、`3\arctan x`、`sin x`），修掉 arctan 被当函数对象返回；
- `sin^2 x` 解析为 `sin(x)^2`；`simplify` 加自定义规则 `sin²+cos²→1`（math.js 默认不认）；
- 提示词补面积/平均值/行列式/反函数/余数/级数/距离/复数模口径，并要求答案与工具结果一致；
- `eval_math_e2e.py` 加 `--ids` 子集模式，支持逐题迭代。

未做：nerdamer 符号积分/因式分解/极限；iOS 计算页真机点按；两份 math.js 副本升级时的 sha256 校验。

### limit 数值极限（2026-11-09 补）

- `math_eval` 新增 `op=limit`：`expr` + `lower` 给趋近点（数值、`inf`、`-inf`），有限点双侧 ε 逼近，无穷用 1e3..1e9 序列；
  收敛要求末三项差值收缩、左右极限一致，结果优先还原漂亮分数并标「数值解」；发散/左右不等/无定义直接报错。
- 新增 28 条 limit SFT（有理式抓最高次、0/0 约分、多项式代值、sin(kx)/x），SFT27e：**58/69（84.1%）**，
  ap_calc 18 / precalc 21 / stats 19，emit 69/69；ap_calc-14/15 两题已通过。
- 代价：v5 相比 v4（同为 58）把 ap_calc-17（最值）与 18（平均值）翻错——17 模型误把 limit 用在最值上，18 仍把区间长度算成 2；
  两版总分一致，v5 能力更全，采用 v5（`sft27e_cas_gguf/`），v4 产物已清理。
- 数值极限边界：振荡函数（sin(1/x)）可能逃过收敛判定；无穷远发散靠采样判定，不做符号证明；对外只宣称「数值极限」。

### 最后优化：v6/v7 均未超过 v5（2026-11-09 收尾）

- 两次尝试：v6 = 提示词 v7c（面积负值重积、平均值改 `(定积分)/(upper-lower)` 调 eval、f''(x) 连调两次、2^k 级数和）
  + 二/复合/平均值/等比各补到 60 条，从 SFT19 重训 → **55/69**；v7 = 从 v5 续训 1,977 行修复集（lr 3e-5，1 epoch）→ **57/69**。
- 判分修复：`score_math_eval.py` 数字兜底会把「最大值为 f'(2)」里的 2 当答案（ap_calc-17 假阳）；
  已改为跳过标识符/函数名后紧跟括号里的数字，`x = …`、`sin(3) ≈ 0.141` 等正常场景不受影响。
- 四组历史输出用修复后判分重评：v5+v7b **58/69**（不变）、v5+v7c 56（不变）、v6 55（不变）、v7 **58→57**（17 题是假阳）。
- 结论：v5 + v7b 是真实最优，v6/v7 及其提示词改动全部回滚（三处提示词恢复 v7b），v7 产物清理；
  提示词层面的补丁（面积顺序/平均值/二阶导/等比）对 1.7B 不奏效，不再加长 system prompt。

### iOS 演示壳接入（2026-11-09，AIY Demo 用）

- `MathEvalTool.swift` 通过 pbxproj 相对路径引用进 iOS target（与 `MathEvalEngine.swift` 同款，不复制代码）；
  `DemoChatView.loadModel()` 启动时注册进 registry（harness/bench 不注册），每轮请求按白名单决定是否启用：
  模型文件名含 `sft27` 时 `tools=["math_eval"]`、temperature 0.2，其余请求保持原白名单（calendar/dispatch），
  因此中途切模型可用，且不改变领队模型的 system 口径（16/16 回归可比）。
- iOS 必须用 `MathEvalEngine(resourceDirectory: "Math")`（Xcode App 是 Math/ 文件夹引用，不是 SPM module bundle）；
  两份 `MathEvalBridge.js` 已校验 sha256 一致。
- 同款 EngineKit 工具环 Mac 实测（SFT27e Q4_K_M）：解方程/极限/导数三题全部真调工具并回填正确；
  **SFT27e 直调日历不可靠**（日期写错、漏 end_time），**SFT20 领队零样本调 math_eval 失败**（复读示例 `eval x^2+3*x`）。
  演示分模型：助理段用领队+工人（16/16），数学段单模型 SFT27e；数学放最后，避免演示中途切回。
- 模型上机：`qwen3-1.7b-sft27e-cas-Q4_K_M.gguf`（1.2G）导入手机模型库，文件名必须含 `sft27` 才启用 math_eval。
