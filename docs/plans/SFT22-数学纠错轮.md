# SFT22 数学纠错轮（计划）

> 2026-11-08 起草。起点：SFT21 领队 final（含 SFT19 学术底子 + SFT20 派单 + SFT21 反问）。
> 触发证据：SFT19 在 69 题 SymPy 客观集上 45/69（65.2%），SFT20 领队回退到 43/69（62.3%）。

## 一、目标

- 把 69 题客观数学集从 62-65% 提到 **≥75%**；
- AP Calc 不低于 60%（当前 SFT20 领队 52%），AP Stats 不低于 55%（当前 57.9%，但不稳定）；
- 不破坏派单/反问：SFT21 的 39 题验收保持（模糊 20、派单 11、chat 8）；
- 不做雅思训练：没有 band 标注与可复核评分，先不拿合成样本硬训。

## 二、数据（从 SFT21 final 继续训）

| 组 | 条数 | 来源 |
|---|---|---|
| 数学纠错 | 2,013 | `train/synthesize/gen_math_sft22.py` 程序化生成，SymPy 算真值 + 模板分步解 |
| 学术回放 | 1,000 | `data/sft19/{ap_calc,precalc,ap_stats,ielts}.jsonl` 分层抽样，防遗忘 |
| 派单回放 | 1,500 | `data/train_sft20_leader/train.jsonl` 抽样 |
| 反问回放 | 1,000 | `data/train_sft21_leader/train.jsonl` 的 clarify 层 |
| 合计 | 5,513 | train / val 9:1 |

数学纠错覆盖面（按实测弱项）：多项式/乘积/商/链式求导、指数对数三角求导、不定/定积分、换元、∞ 与因式分解极限、切线/二阶导/驻点/面积、平均数方差、z/正态、二项、回归、组合排列、IQR、对数指数方程。

## 三、训练配方

- 起点：`checkpoints/qwen3-1.7b-sft21-20261108/final`
- 2 epochs，max-len 2048，per-device-bs 8，grad-accum 8，ZeRO-2，bf16，`--no-think --chunked-ce --save-only-model`
- save-steps 1000（只留 final 与末步权重，磁盘紧张）
- 冒烟 3 步必须同时出 loss/eval_loss
- 产物：`checkpoints/qwen3-1.7b-sft22-<date>/final`，Q5_K_M / Q4_K_M

## 四、验收

1. 69 题数学客观集（同一份 `train/eval/math_eval.json`，温度 0）；
2. SFT21 的 39 题（模糊 20 / 派单 11 / chat 8）；
3. 若数学 ≥75% 且派单 ≥10/11、模糊 ≥18/20，则替换 iOS 领队模型；否则保留 SFT21，记录失败原因。

## 五、回滚

SFT21 final 与 Q5/Q4 保留；SFT22 单独目录，评测不通过不替换。

## 六、雅思

本轮不训。前置条件：建立 10-20 篇 held-out 写作题 + 按 IELTS 四项 band descriptors 的可复核评分（人工或强模型 judge，双评取一致），再决定是否补数据。
