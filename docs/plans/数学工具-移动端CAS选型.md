# 数学工具：移动端 CAS 选型与边界（2026-11-08）

## 一、结论先行

- **轻量数学工具（手机端离线）：局限性不高。** 用 math.js / nerdamer / Algebrite 这类 JS CAS 放进 JavaScriptCore，体积 0.2–2MB，单次表达式毫秒级，完全离线，不碰服务器。
- **完整 SymPy（手机端离线）：局限性高。** Pyodide + Python 运行时约 21MB，加 NumPy 约 7MB，再加 SymPy，加载几十 MB；启动慢、内存峰值高，纯 Python 循环比原生慢 1–16 倍。技术上能跑，但不值得为一个“计算器”付这个代价。
- **真正难的不是算，而是“把中文题变成表达式”。** 模型仍然要负责理解题意、列式、选择工具；工具只保证算得准。词题理解错，工具也算错。

## 二、候选方案对比

| 方案 | 体积 | 能力 | 手机端限制 | 建议 |
|---|---|---|---|---|
| math.js（JavaScriptCore） | 729KB min / 197KB gzip（npm 15.2.0 实测） | 表达式解析、化简、求导、矩阵、统计、单位；**无符号积分**，积分只能数值 | 需自己写数值积分；无假设/定义域推理 | **一期首选**，覆盖算术/求导/统计/矩阵 |
| nerdamer（JavaScriptCore） | 核心 536KB min / 151KB gzip，加 Calculus/Solve 扩展约 1MB | 符号求导、积分、解方程、化简 | 覆盖不如 SymPy；复杂积分会失败；性能一般 | **二期首选**，补符号积分/解方程 |
| Algebrite（JavaScriptCore） | 334KB min / 79KB gzip（npm 1.4.0 实测） | JS CAS，含 integral、roots、simplify、矩阵 | 更新慢（1.4.0 后基本停更）；复杂表达式慢 | 与 nerdamer 二选一，体积最小 |
| Pyodide + SymPy（WebView/WASM） | 核心运行时约 12MB（wasm 8.6 + stdlib 2.4 + js 1.1），加 SymPy/NumPy 后 20MB+ | 最全：符号积分、级数、假设、LaTeX | 启动慢、内存高、WASM 在 iOS 无 JIT 更慢；WebView 集成复杂 | **三期再评估**，不做默认 |
| 原生 Swift（自写 parser + Swift Numerics） | <1MB | 四则/函数/数值积分/统计 | 符号积分和化简工作量大，数学边界容易写错 | 只做数值/统计工具时可用，不建议自写 CAS |

## 三、产品落地建议（按实测错因排优先级）

我们 69 题客观评测里，模型错得最多的是：
1. 求导系数/乘积/商/链式法则；
2. 定积分计算；
3. 极限；
4. 统计公式（方差、二项、回归、组合、IQR）；
5. arctan 等反三角函数求导。

这些恰好是工具最擅长的。建议工具集分三层：

1. **calc**：四则、分数、幂、函数求值（math.js，精确分数用 BigNumber/Fraction）。
2. **derivative / simplify**：符号求导、化简（math.js）。
3. **integrate_def / integrate_indef / solve / stats**：
   - 定积分先用 math.js 数值积分（高精度采样），符号积分用 nerdamer/Algebrite；
   - 统计直接给 mean/median/variance/std/z/binomial/regression/combination 等函数，避免模型手算；
   - solve 用 nerdamer 解方程/方程组。
4. **校验层**：工具返回结果后，用数值回代/求导验证（例如积分结果求导应还原被积函数），不通过就报错，不让模型硬编。

## 四、边界与风险

- **不解决“读懂题”**：应用题、证明题、FRQ 评分仍然靠模型；工具只处理结构化表达式。
- **表达式入口要约束**：模型必须输出 `{"expr": "...", "var": "x", "a": ..., "b": ...}` 这类结构化参数，不能把自然语言直接塞给工具。
- **iOS 集成成本**：JavaScriptCore 是系统框架，离线可用；需要处理 JS 异常、超时（建议 2s 上限）、内存峰值和线程隔离。
- **体积不是问题**：1–2MB 相对 1.1GB 模型可以忽略；启动时懒加载，不拖慢首屏。
- **App Store**：内嵌 JS 解释器执行自带脚本是允许的；不要下载并执行远程 JS。

## 五、验收标准

- 69 题客观集里，凡是“纯计算/求导/积分/统计”的题，工具路径正确率 ≥95%；
- 工具调用失败/超时率 <2%，单次 P95 <300ms；
- 模型负责列式，工具负责算，最终答案以工具结果为准；
- 与纯模型路径对比，数学总分提升 ≥15 个百分点（目标从 65% 到 ≥80%）。

## 六、参考

- math.js 求导/化简：[math.js derivative](https://mathjs.org/docs/reference/functions/derivative.html)、[math.js simplify](https://mathjs.org/docs/reference/functions/simplify.html)
- nerdamer：[官网](https://nerdamer.com/)、[GitHub](https://github.com/jiggzson/nerdamer)
- Algebrite：[GitHub](https://github.com/davidedc/Algebrite)
- Pyodide：[官方 quickstart](https://pyodide.org/en/stable/usage/quickstart.html)
