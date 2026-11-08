#!/usr/bin/env python3
"""清洗合成/拼装池中的 202X/XXXX 占位符残留（SFT17 幻觉率根因：
teacher 举例未知日期时写 202X年X月X日，模型学会「日期没把握→输出 X 模板」）。

用法：python3 fix_placeholder_sft.py --dir data/sft [--backup /home/ubuntu/backups/sft_ph_bak-20261102]
规则按「最长优先」顺序替换；改前按相对路径备份；终检占位符清零 + 逐行 JSON 有效。
"""
import argparse
import glob
import json
import os
import shutil

# 最长优先：先匹配带上下文的完整模板，最后兜底裸 202X/XXXX
RULES = [
    ("（建议标注具体年月日，如 202X年X月X日）", "（建议标注具体年月日）"),
    ("（如：202X年X月X日）", ""),
    ("（例如：202X年X月X日）", ""),
    ("[日期：202X年X月X日]", "[日期]"),
    ("[日期：XXXX年XX月XX日]", "[日期]"),
    ("[具体日期，如：202X年X月X日]", "[具体日期]"),
    ("**202X年X月X日（星期X）上午**", "**（日期待定）上午**"),
    ("**202X年X月X日（明天）上午**", "**明天上午**"),
    ("[XXXX]", "[待定]"),
    ("202X年X月X日", "具体日期"),
    ("XXXX年XX月XX日", "具体日期"),
    ("202X", "具体日期"),
    ("XXXX", "具体日期"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sft")
    ap.add_argument("--backup", default="/home/ubuntu/backups/sft_ph_bak-20261102")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.jsonl")))
    if not files:
        print(f"{args.dir} 下没有 jsonl")
        return 1
    total_hits = 0
    for fn in files:
        with open(fn, encoding="utf-8") as f:
            lines = f.readlines()
        hits = 0
        new_lines = []
        for ln in lines:
            for pat, rep in RULES:
                if pat in ln:
                    hits += ln.count(pat)
                    ln = ln.replace(pat, rep)
            new_lines.append(ln)
        if not hits:
            continue
        bak = os.path.join(args.backup, os.path.relpath(fn, args.dir))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(fn, bak)
        with open(fn, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        total_hits += hits
        print(f"{os.path.basename(fn)}: 替换 {hits} 处")

    ok = True
    for fn in files:
        rest = bad = 0
        with open(fn, encoding="utf-8") as f:
            for ln in f:
                if "202X" in ln or "XXXX" in ln:
                    rest += 1
                if "20XX" in ln:
                    rest += 1  # 兜底扫描年号占位，一并计入残留
                try:
                    json.loads(ln)
                except Exception:
                    bad += 1
        if rest or bad:
            print(f"{os.path.basename(fn)}: 残留 {rest} 行 | JSON 坏行 {bad}")
            ok = False
        else:
            print(f"{os.path.basename(fn)}: 残留 0 | JSON 全通过")
    print(f"总替换: {total_hits}")
    print("终检:", "通过" if ok else "不通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
