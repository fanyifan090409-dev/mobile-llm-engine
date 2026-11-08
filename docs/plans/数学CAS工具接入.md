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

- 纯计算子集 **56/56（100%）**：ap_calc 17、precalc 20、ap_stats 19；
- P95 **99.6ms**、最慢 224ms（Simpson 20000 段定积分）、math.js 首次载入 41ms；
- 排除 13 题：不定积分 2、极限 2、最值/切线/二阶/参数方程 4、化简/因式分解/方程组/圆 5 —— 需要推导或二期能力；
- 已修回归：负整数符号（mathjs Fraction 的 `n` 无符号）、隐式乘法 `5x` 变量漏替换、`\cdotx` 非法 LaTeX。

未做（后续）：

- iOS 壳的计算入口与 SwiftUI 页面（引擎类可直接复制，资源走 `Bundle.main`）；
- 二期 1,000 条 `math_eval` 工具调用 SFT 与 69 题端到端验收。
