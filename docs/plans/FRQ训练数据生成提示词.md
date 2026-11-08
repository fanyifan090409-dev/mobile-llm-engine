# FRQ 数据生成提示词（给大模型用，2026-11-08）

## 一、本地 FRQ 家底

- `train/eval/private/ap_calc_bc_frq_2022_2024.json`：21 题（2022/2023/2024 官方 FRQ，含小题、官方答案/评分点）。
- `train/eval/private/ap_calc_bc_frq_2025_2026.json`：12 题（2025/2026 官方 FRQ）。
- 合计 33 题，约 120 个小题；来源为用户提供的 College Board 官方 PDF，仅本地训练/评测，不进公开仓库。
- 缺口：**AP Statistics FRQ 0 题**（69 题里 Stats 最弱，47.4%）；**AP Precalculus FRQ 0 题**。建议补：
  - https://apcentral.collegeboard.org/courses/ap-statistics/exam/past-exam-questions
  - https://apcentral.collegeboard.org/courses/ap-precalculus/exam

## 二、主提示词（复制给大模型）

```text
你是 AP Calculus BC / AP Statistics 阅卷人，也是教材作者。下面给你一道官方 FRQ（题面、小题、官方答案、评分点）。请把它转成适合 1.7B 小模型学习的中文解题样本。

【硬性规则】
1. 只使用题面给出的条件；不增删数据、不改变情境；图形题保留图注描述。
2. 官方答案/评分点是锚点：最终答案必须包含锚点数值；允许四舍五入，但不能改变数值或结论。
3. 每个小题都必须回答；不能只做一部分，不能漏问“解释/说明/单位”。
4. 【解答】逐步推导：每一步写“为什么”（用了哪个定理/公式/定义），数值计算写出代入过程，不跳步。
5. 数学用纯文本/Unicode：∫ √ π ≤ ² ³ ′ ≈ ∞；不要 LaTeX $...$，不要 Markdown 代码块。
6. 中文讲解；专业术语可保留英文；不写“显而易见/不难发现”，不写“作为 AI”。
7. 不确定的步骤标 [待核验]，不要编造；官方答案与题面冲突时，以官方答案为准，并在【思路】里说明。
8. 只输出 JSON，不要任何解释文字；字符串内换行用 \n，确保能被 json.loads 解析。

【输出结构】
{
  "year": 2022,
  "num": 1,
  "subject": "AP Calculus BC",
  "main": {
    "user": "完整中文题面（含所有小题、数据表、图形描述）",
    "assistant": "【思路】...\n\n【解答】...\n\n【答案】..."
  },
  "parts": [
    {
      "id": "A",
      "user": "A 小题题面 + 必要背景",
      "assistant": "【思路】...\n\n【解答】...\n\n【答案】..."
    }
  ],
  "rubric": ["P1 ...", "P2 ..."],
  "cas_hints": [
    {
      "part": "A",
      "op": "integrate_def",
      "expr": "7.6*atan(0.2*t)",
      "variable": "t",
      "lower": 0,
      "upper": 4,
      "why": "求平均值的积分"
    }
  ]
}

【cas_hints 规则】
- 只列适合 CAS 的纯计算步骤：eval / derivative / simplify / integrate_def / integrate_indef / solve / stats。
- 只给表达式和参数，不要给结果（结果由 CAS 计算）。
- 表达式用 math.js 语法：* 乘、^ 幂、函数 asin/acos/atan/log/sqrt/exp；不要用 Unicode 积分号。
- 没有适合 CAS 的步骤就给空数组。

【自检】
- 每个 part 都有 assistant；main 覆盖全部 part；
- 所有官方锚点数值都出现在【答案】里；
- 没有 $、没有代码块、JSON 可解析；
- 单位、方向、符号（正负）没漏。

下面是真题：
{{把题目 JSON 粘在这里}}
```

## 三、变式提示词（可选，主样本跑完后用）

```text
基于你刚输出的 main，生成 3 道同构变式：只改数字/函数/情境，解题路径和问题结构不变；难度与原题相当；每题给 user/assistant/cas_hints；变式答案必须自洽；输出 JSON 数组，不要解释。
```

变式输出存 `variants-<year>-q<num>.json`（导入器按这个文件名找原题、归入同一数据池）。变式没有官方答案，自动防线是把 `cas_hints` 逐条数值执行，再回查【答案】区：eval 结果、定积分结果、导数值必须都写在答案里，增减方向必须和数值导数符号一致。所以变式的 `cas_hints` 不是可选项，写错会被整条拒收。

## 四、使用方式

- 33 份「主提示词 + 题目」已合成单文件，在 `train/eval/private/frq_prompts/`（`2022-q1.txt` … `2025-q6.txt`），一个文件贴一次即可；变式提示词在同目录 `_variant_prompt.txt`。
- 输出存 `train/eval/private/frq_bigmodel_out/<year>-q<num>.json`，变式存 `variants-<year>-q<num>.json`。
- 如果输出被截断：先要 `main`，再单独要 `parts`，最后要 `cas_hints`，分三次输出。
- 33 题全部跑完后，本机执行：

  ```bash
  python3 train/synthesize/import_frq_bigmodel.py \
    --frq-data train/eval/private/ap_calc_bc_frq_2022_2024.json \
              train/eval/private/ap_calc_bc_frq_2025_2026.json \
    --indir train/eval/private/frq_bigmodel_out \
    --outdir train/synthesize/out_frq
  ```

  校验不过的样本会逐条写进 `report.json` 的原因字段，改完重跑即可。
- 官方真题受版权保护，只用于本地训练；不要上传到公开仓库。

## 五、验收（脚本已实现）

- 锚点命中：官方答案数字必须出现在整题答案区；
- 结构完整：main + 每个 part 都有【思路】【解答】【答案】；
- 数值一致：`cas_hints` 当程序执行，eval/定积分/导数值必须回查得到，方向不能反（已用改错用例反向验证：体积差 0.3、方向写反、变化率写错都会被拒）；
- 变体：小题 A-D 齐全、`cas_hints` 覆盖到有效小题、文件名合规；
- 首批验收（2026-11-08，31 题）：从 31 个 Qoder 会话转录里直接提取，32 个文件（31 正题 + 3 变体）全部通过，共 151 条（train 128 / val 23）；抽查 2022-q36 B、2023-q1 C、2025-q1 D、2026-q2 A 四例，最终数值与官方锚点完全一致。
- 缺两题（源数据问题，不是模型问题）：
  - 2022-q3：本地题录缺附图三条线段的端点坐标，A/C/D 无法作答；对应会话去 College Board 抓原卷，被反爬页挡住。
  - 2024-q4：没有派发会话；题录里锚点（−12/4/3、−1.5/−0.5/0）够推 A/B/C，但附图描述不完整，暂不生成。
- 校验器口径：正题的 hint 常是中间量（积分后再除区间长度、求导验证单调），不要求出现在答案区，正确性由官方锚点兜底；变体没有官方答案，hint 必须对上数值和方向。
- 剩余人工项：抽 10 题核对推导步骤，错一步退回重生成。
- 训练结果（SFT26，2026-11-08）：128 条 FRQ + 1,314 条 SFT25 回放训 LoRA，数学客观分仍 47/69，与 SFT25 持平；留出 FRQ 与训练集内题都出现幻觉/公式错，1.7B 容量不足。**数据留作 CAS 二期工具调用 SFT 原料，不再直接训解题。**
