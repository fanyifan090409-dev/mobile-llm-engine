#!/usr/bin/env python3
"""AP Calc BC 真题转化链（Pro 机官方 CodeBuddy CLI）：
读 ap_calc_bc_frq_2022_2024.json → 每题产 1 主样本 + 4 同构变式 →
【思路】【解答】【答案】契约 → 官方锚点硬校验 → 80/20 分池（holdout 4 题）。

用法：python3 convert_frq_cloud.py --data ap_calc_bc_frq_2022_2024.json \
        --official-dir official_txt --outdir frq_converted
"""
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time

CLI = os.path.expanduser("~/.codebuddy/bin/codebuddy")
TIMEOUT = 900

# holdout 题（20% = 4 题，固定划分保证训练/评测可复现；按题型均匀：参数方程/表值/级数/图题各一）
HOLDOUT = [(2022, 2), (2023, 6), (2024, 1), (2024, 4)]

# 每题官方锚点（转化输出【答案】必须全部包含；去空格后子串匹配）
ANCHORS = {
    (2022, 1): ["2263.337"],
    (2022, 2): ["2.831", "10.556", "−1.732", "−0.566"],
    (2022, 3): ["f′(−1/2)=1"],
    (2022, 4): ["e^"],
    (2022, 5): [],
    (2022, 6): [],
    (2022, 36): ["1.253", "0.651", "0.575"],
    (2022, 37): ["0.384"],
    (2022, 38): ["[2,12)", "2/5"],
    (2023, 1): ["0.614", "−0.00588"],
    (2023, 2): ["1.254", "3.342", "0.629", "6.035"],
    (2023, 3): ["22.5", "35e^(−t/4)"],
    (2023, 4): ["neither", "(−2,0)", "(4,6)", "1", "7−π"],
    (2023, 5): ["10−12ln2", "48", "−4"],
    (2023, 6): ["x²/2", "x⁴/4"],
    (2024, 1): ["985", "40.329", "递增"],
    (2024, 2): ["12.305", "15.902", "−1.174", "5.222"],
    (2024, 3): ["t=π", "3e^(sin(t/2))"],
    (2024, 4): ["−12", "−1.5"],
    (2024, 5): ["37", "11π", "16cos(t/4)"],
    (2024, 6): ["发散", "125/144", "5/256", "6", "3"],
}


def chat_cloud(user_text):
    """官方 CLI 单次补全，返回文本；失败/空返回 ''。"""
    for attempt in range(3):
        try:
            r = subprocess.run([CLI, "-p", user_text], capture_output=True,
                               text=True, timeout=TIMEOUT)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        time.sleep(10)
    return ""


def parse_json_block(out):
    """从 CLI 输出提取 JSON 对象（容错：剥 ```json 围栏、找最外层 {}）。"""
    out = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", out.strip())
    try:
        return json.loads(out)
    except Exception:
        pass
    # 找第一个 { 到最后一个 } 的切片再试
    s, e = out.find("{"), out.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(out[s:e + 1])
        except Exception:
            pass
    return None


def check_anchor(answer_text, anchors):
    """锚点硬校验：去空格后子串匹配，answer 文本必须包含全部锚点。返回缺失列表。"""
    # 归一化 Unicode 数学符号：锚点手抄自评分标准带 U+2212 减号/U+2032 撇号，
    # 模型输出常为 ASCII -/'，纯子串匹配会误判缺失（2026-11-02 实发：−1.174 连挂两次）
    def norm(s):
        return re.sub(r"\s+", "", s.replace("−", "-").replace("′", "'"))

    flat = norm(answer_text)
    missing = [a for a in anchors if norm(a) not in flat]
    return missing


def check_blocks(assistant):
    """标记块校验：思路/解答/答案三块齐全。"""
    return all(f"【{b}】" in assistant for b in ("思路", "解答", "答案"))


def check_latex(text):
    """LaTeX 残缺检查：孤立 $ 或以 \\ 结尾。"""
    n = text.count("$")
    if n % 2 != 0:
        return False
    for m in re.finditer(r"\$[^$]*\$", text):
        if m.group(0).rstrip().endswith("\\"):
            return False
    return True


def build_prompt(q, official_text):
    """构建单题转化 prompt（中文）。"""
    key = (q["year"], q["num"])
    anchors = ANCHORS.get(key, [])
    parts = q["parts"]
    answers = "\n".join(f"- ({p['id']}) {p['prompt']}\n  官方答案/锚点：{p.get('answer', '')}"
                        for p in parts)
    figure_note = ""
    if q.get("figure"):
        figure_note = f"\n## 附图说明\n{q['figure']}"
    official_note = ""
    if official_text:
        official_note = ("\n## 官方题面原文（PDF 文本层，含乱序伪影，仅作公式重建对拍依据）\n"
                         f"{official_text[:6000]}")
    lines = [
        "你是 AP Calculus BC 真题转化器。把真题转成适合 1.7B 小模型学习的解题训练样本。",
        f"## 输入真题（JSON）\n{q['statement']}",
        f"## 小题\n{answers}",
        figure_note,
        official_note,
        "## 输出要求",
        "1. 公式修复：题面/官方原文中标注 ⚠️ 或残片乱序的公式，按官方答案锚点重建正确公式；重建公式必须使锚点数值全部命中（每步代入验证）。",
        "2. 主样本：user = 完整中文题面（含所有小题与数据表），assistant = 【思路】【解答】【答案】三块：",
        "   - 【思路】2-4 句解题规划：用什么方法、为什么适用",
        "   - 【解答】逐小题分步编号，每步给理由（为什么这一步），不跳步，数值计算写出代入过程",
        "   - 【答案】逐小题最终结果（含单位），与官方锚点一致",
        "3. 变式 4 条：同构变式（改数据不改解法路径，数字换成好算的值），每条 user = 变式题面、assistant = 同规格三块解答。变式答案自行验算保证正确。",
        "4. 语言：中文（数学专有名词可英文）；公式用 LaTeX $…$；不写「显而易见」「不难发现」式空话。",
        "5. 输出纯 JSON（勿加解释文字）：",
        '{"main": {"user": "...", "assistant": "..."}, "variants": [{"user": "...", "assistant": "..."}, ...]}',
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ap_calc_bc_frq_2022_2024.json")
    ap.add_argument("--official-dir", default="official_txt")
    ap.add_argument("--outdir", default="frq_converted")
    ap.add_argument("--start", type=int, default=0, help="从第几题开始（断点续跑）")
    args = ap.parse_args()

    d = json.load(open(args.data, encoding="utf-8"))
    qs = d["questions"]
    os.makedirs(args.outdir, exist_ok=True)

    official = {}
    for y in (2022, 2023, 2024):
        p = os.path.join(args.official_dir, f"official-{y}-frq.txt")
        if os.path.exists(p):
            official[y] = open(p, encoding="utf-8").read()

    train_f = open(os.path.join(args.outdir, "train.jsonl"), "a", encoding="utf-8")
    hold_f = open(os.path.join(args.outdir, "holdout.jsonl"), "a", encoding="utf-8")
    report = []

    for i, q in enumerate(qs):
        if i < args.start:
            continue
        key = (q["year"], q["num"])
        is_hold = key in HOLDOUT
        print(f"[{i+1}/{len(qs)}] {q['year']} Q{q['num']} {'HOLDOUT' if is_hold else 'train'}", flush=True)
        prompt = build_prompt(q, official.get(q["year"], ""))
        ok = False
        for attempt in range(3):
            out = chat_cloud(prompt)
            if not out:
                print("  CLI 空回复", flush=True)
                continue
            parsed = parse_json_block(out)
            if not parsed:
                print("  JSON 解析失败", flush=True)
                continue
            main_a = parsed.get("main", {}).get("assistant", "")
            anchors = ANCHORS.get(key, [])
            missing = check_anchor(main_a, anchors)
            if missing:
                print(f"  锚点缺失: {missing}（尝试 {attempt+1}）", flush=True)
                # 追加纠错提示重试
                prompt_fix = (f"上一轮输出【答案】缺少官方锚点 {missing}。请重算修正后重新输出完整 JSON"
                              f"（锚点必须全部出现，逐小题自查）。原要求不变。")
                prompt = prompt + "\n" + prompt_fix
                continue
            if not check_blocks(main_a):
                print("  标记块缺失", flush=True)
                continue
            if not check_latex(main_a):
                print("  LaTeX 残缺", flush=True)
                continue
            # 组装样本
            samples = []
            m = parsed["main"]
            h = hashlib.sha256(json.dumps([m], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
            samples.append({"messages": [{"role": "user", "content": m["user"]},
                                         {"role": "assistant", "content": main_a}],
                            "category": "ap_calc", "form": "solve_frq",
                            "source": f"{q['year']}-Q{q['num']}-main", "hash": h})
            for j, v in enumerate(parsed.get("variants", [])[:4]):
                va = v.get("assistant", "")
                if not check_blocks(va) or not check_latex(va):
                    continue
                h = hashlib.sha256(json.dumps([v], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
                samples.append({"messages": [{"role": "user", "content": v["user"]},
                                             {"role": "assistant", "content": va}],
                                "category": "ap_calc", "form": "solve_frq_variant",
                                "source": f"{q['year']}-Q{q['num']}-v{j+1}", "hash": h})
            sink = hold_f if is_hold else train_f
            for s in samples:
                sink.write(json.dumps(s, ensure_ascii=False) + "\n")
            sink.flush()
            report.append({"key": f"{q['year']}-Q{q['num']}", "holdout": is_hold,
                           "variants": len(samples) - 1, "attempts": attempt + 1})
            print(f"  主样本 + {len(samples)-1} 变式 ✓（第 {attempt+1} 次调用）", flush=True)
            ok = True
            break
        if not ok:
            report.append({"key": f"{q['year']}-Q{q['num']}", "holdout": is_hold,
                           "variants": 0, "attempts": 3, "FAILED": True})
            print("  3 次尝试均失败，跳过（记录进 report）", flush=True)

    train_f.close()
    hold_f.close()
    json.dump(report, open(os.path.join(args.outdir, "report.json"), "w"),
              ensure_ascii=False, indent=1)
    n_ok = sum(1 for r in report if "FAILED" not in r)
    n_train = sum(1 for r in report if "FAILED" not in r and not r["holdout"])
    n_hold = sum(1 for r in report if "FAILED" not in r and r["holdout"])
    print(f"\n完成：{n_ok}/{len(report)} 题成功（train {n_train} / holdout {n_hold}）")


if __name__ == "__main__":
    main()
