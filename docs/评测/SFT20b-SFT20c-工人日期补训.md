# SFT20b/SFT20c 工人日期补训评测报告

> 日期：2026-11-06。模型：`qwen3-0.6b-sft20c-20261106` Q5_K_M。评测口径：60 题 held-out、temperature 0、`enable_thinking=false`（空思考块注入）。

## 一、结论

**SFT20c 采用。** 日期 60 题 **56/60（93.3%）**，其中「下周X」**22/22** 全对；8 题 worker 回归 **8/8**，工具选择与 JSON/schema 全对，相对日期泄漏 0。

前提：**生产推理必须做两件事**——日历/提醒工人输入追加「本周/下周/下下周」日期表；assistant 回合注入空思考块（`enable_thinking=false`）。少任一条，SFT20c 会退化到 46.7% 或直接复读输入。

## 二、三版对比（同一套 60 题）

| 指标 | SFT20 工人 | SFT20b（无表直接训） | SFT20c 带表 | SFT20c 无表对照 |
|---|---|---|---|---|
| 日期 exact | 15/60（25.0%） | 31/60（51.7%） | **56/60（93.3%）** | 28/60（46.7%） |
| 下周X | 0/22 | 2/22 | **22/22** | 2/22 |
| 这周X | 1/8 | 5/8 | **8/8** | 5/8 |
| 相对（明天/后天/今晚…） | 6/8 | 7/8 | **8/8** | 7/8 |
| 绝对（M月D日） | 4/8 | 8/8 | 7/8 | 7/8 |
| 下个月D号 | 2/6 | 6/6 | **6/6** | 6/6 |
| 边界（跨月/跨年/闰日） | 2/8 | 3/8 | 5/8 | 1/8 |
| emit / JSON / schema | 60/60 | 60/60 | 60/60 | 60/60 |
| 相对日期泄漏 | 0 | 0 | 0 | 0 |
| 8 题 worker 回归 | 8/8 | 8/8 | **8/8** | — |

> 8 题回归在补上 `enable_thinking=false` 后三版都是 8/8。此前 SFT20 的 7/8、SFT20b 的 6/8（摘要格式崩）是评测端模板错配，不是模型退化。

## 三、剩余 4 个失败（SFT20c 带表）

| 题 | 输入要点 | 模型输出 | 正确值 | 性质 |
|---|---|---|---|---|
| 绝对 | 今天 2027-02-01，「2月29日」 | 2027-02-29 | 2028-02-29 | 平年闰日知识 |
| 边界 | 下周一 23:30，时长 3 小时 | end `24:30` | 次日 02:30 | 小时进位格式 |
| 边界 | 今天 2026-12-30，「后天」 | 2026-12-01 | 2027-01-01 | 跨年进位 |
| 边界 | 今天 2028-02-28，「明天」 | 2028-03-01 | 2028-02-29 | 闰日 |

前三类都是低频边界，不影响主路径；核心星期推算已 22/22。

## 四、关键坑

1. **日期表必须进训练分布**：零样本把表塞进提示词，SFT20b 把输入整段复读（emit 1/60）。SFT20c 用 4200 条带表样本训练后才学会抄表。
2. **`--no-think` 训练的模型，推理端必须 `enable_thinking=false`**：llama-server 只加 `--jinja` 不会注入空思考块；SFT20b 对模板错配较鲁棒，SFT20c 极敏感，表现为复读输入或聊天确认，极易误判为量化坏了。
3. 0.6B 本身不会星期心算：SFT20b 数据 4000 条、训练 loss 0.01，下周X 仍 2/22；查表是容量内的可行解。

## 五、产物与复现

- 模型：`train/gguf/qwen3-0.6b-sft20c-20261106/qwen3-0.6b-sft20c-Q5_K_M.gguf`（526M）、`Q4_K_M`（462M）
- 数据：`train/synthesize/date_sft20c/`（train 5872 / val 96）；生成器 `gen_date_worker.py`，加表 `add_date_table.py`，独立反解 QC `qc_date_worker.py`
- 评测集：`train/eval/date_worker_eval.json`（60 题）、`date_worker_eval_table.json`（带表版）
- 结果：`train/nightly/work/sft20b_date/sft20c_date_table_thinkoff/`、`sft20c_date_plain_thinkoff/`、`sft20_date_thinkoff/`、`sft20b_date_thinkoff/`
- 回归：`train/nightly/work/sft20_dispatch/sft20c_worker_Q5_thinkoff/`

```bash
bash train/eval/run_date_eval.sh <gguf> 8124 <tag> [date_worker_eval_table.json]
bash train/eval/run_sft20_eval.sh <gguf> worker 8125 <tag>
```
