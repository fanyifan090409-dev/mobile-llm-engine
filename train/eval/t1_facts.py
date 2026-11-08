#!/usr/bin/env python3
"""Task 1 确定性事实清单：结构化数据 → 可逐条核对的事实句。

目的：把「数字/排名/趋势」从模型手里拿走，模型只负责 overview 和衔接。
用法：
  python3 t1_facts.py --data train/eval/ielts_t1_structured.json
  python3 t1_facts.py --data ... --id t1-line-internet
"""
import argparse
import json


def n(v, unit=""):
    s = f"{v:g}"
    return f"{s}%" if unit == "%" else s


def line_facts(d):
    unit = d.get("unit", "")
    years = d["years"]
    series = d["series"]
    names = list(series)
    facts = []
    for i, y in enumerate(years):
        vals = ", ".join(f"{k} = {n(series[k][i], unit)}" for k in names)
        facts.append(f"In {y}: {vals}.")

    for k in names:
        vals = series[k]
        chg = vals[-1] - vals[0]
        direction = "rose" if chg > 0 else ("fell" if chg < 0 else "stayed flat")
        if chg == 0:
            facts.append(f"{k} stayed at {n(vals[0], unit)} from {years[0]} to {years[-1]}.")
        else:
            facts.append(f"{k} {direction} from {n(vals[0], unit)} in {years[0]} to "
                         f"{n(vals[-1], unit)} in {years[-1]} ({chg:+g} points).")
        hi = max(range(len(vals)), key=lambda i: vals[i])
        lo = min(range(len(vals)), key=lambda i: vals[i])
        facts.append(f"{k} peaked at {n(vals[hi], unit)} in {years[hi]} and was lowest "
                     f"at {n(vals[lo], unit)} in {years[lo]}.")

    # 每年最高/最低
    top_each = [max(names, key=lambda k: series[k][i]) for i in range(len(years))]
    low_each = [min(names, key=lambda k: series[k][i]) for i in range(len(years))]
    if len(set(top_each)) == 1:
        facts.append(f"{top_each[0]} was the highest series in every year.")
    else:
        facts.append("Highest series by year: " + ", ".join(f"{y}={t}" for y, t in zip(years, top_each)) + ".")
    if len(set(low_each)) == 1:
        facts.append(f"{low_each[0]} was the lowest series in every year.")
    else:
        facts.append("Lowest series by year: " + ", ".join(f"{y}={t}" for y, t in zip(years, low_each)) + ".")

    # 交叉
    for i in range(1, len(years)):
        for a in names:
            for b in names:
                if a >= b:
                    continue
                before = series[a][i - 1] - series[b][i - 1]
                after = series[a][i] - series[b][i]
                if before < 0 < after:
                    facts.append(f"{a} overtook {b} between {years[i-1]} and {years[i]}.")
                elif before > 0 > after:
                    facts.append(f"{b} overtook {a} between {years[i-1]} and {years[i]}.")

    chg = {k: series[k][-1] - series[k][0] for k in names}
    best = max(names, key=lambda k: chg[k])
    worst = min(names, key=lambda k: chg[k])
    facts.append(f"Largest overall increase: {best} ({chg[best]:+g} points).")
    facts.append(f"Smallest overall change: {worst} ({chg[worst]:+g} points).")
    return facts


def bar_facts(d):
    unit = d.get("unit", "")
    cats = d["categories"]
    groups = d["groups"]
    facts = []
    for g, vals in groups.items():
        facts.append(f"{g}: " + ", ".join(f"{c} = {n(v, unit)}" for c, v in zip(cats, vals)) + ".")
        facts.append(f"{g} total = {n(sum(vals), unit)}.")
        hi = max(range(len(vals)), key=lambda i: vals[i])
        lo = min(range(len(vals)), key=lambda i: vals[i])
        facts.append(f"{g}: highest is {cats[hi]} ({n(vals[hi], unit)}); lowest is {cats[lo]} ({n(vals[lo], unit)}).")

    gnames = list(groups)
    if len(gnames) == 2:
        a, b = gnames
        diffs = [(cats[i], groups[a][i] - groups[b][i]) for i in range(len(cats))]
        big = max(diffs, key=lambda x: abs(x[1]))
        facts.append(f"Largest group difference is in {big[0]}: {a} vs {b} = "
                     f"{n(groups[a][cats.index(big[0])], unit)} vs {n(groups[b][cats.index(big[0])], unit)}.")
        for c, dv in diffs:
            facts.append(f"Difference in {c}: {a} minus {b} = {dv:+g}.")
    return facts


def pie_facts(d):
    unit = d.get("unit", "%")
    years = list(d["years"])
    cats = list(d["years"][years[0]])
    facts = []
    for y in years:
        items = sorted(d["years"][y].items(), key=lambda kv: kv[1], reverse=True)
        facts.append(f"{y}: " + ", ".join(f"{k} {n(v, unit)}" for k, v in items) + ".")
        facts.append(f"{y} largest: {items[0][0]} ({n(items[0][1], unit)}); smallest: "
                     f"{items[-1][0]} ({n(items[-1][1], unit)}).")
    if len(years) == 2:
        a, b = years
        for c in cats:
            ch = d["years"][b][c] - d["years"][a][c]
            facts.append(f"{c}: {n(d['years'][a][c], unit)} in {a} -> "
                         f"{n(d['years'][b][c], unit)} in {b} ({ch:+g} points).")
        changes = {c: d["years"][b][c] - d["years"][a][c] for c in cats}
        up = max(cats, key=lambda c: changes[c])
        down = min(cats, key=lambda c: changes[c])
        facts.append(f"Largest increase: {up} ({changes[up]:+g} points).")
        facts.append(f"Largest decrease: {down} ({changes[down]:+g} points).")
    return facts


def table_facts(d):
    cols = d["columns"]
    rows = d["rows"]
    facts = []
    for i, col in enumerate(cols):
        order = sorted(rows, key=lambda r: rows[r][i], reverse=True)
        facts.append(f"{col} ranking: " + "; ".join(
            f"{j+1}. {r} = {n(rows[r][i])}" for j, r in enumerate(order)) + ".")
        facts.append(f"{col} range: {n(rows[order[-1]][i])} to {n(rows[order[0]][i])} "
                     f"(gap {n(rows[order[0]][i] - rows[order[-1]][i])}).")
    for r, vals in rows.items():
        facts.append(f"{r}: " + ", ".join(f"{c} = {n(v)}" for c, v in zip(cols, vals)) + ".")
    if len(cols) >= 2:
        top0 = max(rows, key=lambda r: rows[r][0])
        top1 = max(rows, key=lambda r: rows[r][1])
        if top0 != top1:
            facts.append(f"The top row differs by column: {top0} leads {cols[0]}, "
                         f"{top1} leads {cols[1]}.")
    return facts


def process_facts(d):
    steps = d["steps"]
    facts = [f"The process has {len(steps)} stages."]
    for i, s in enumerate(steps, 1):
        facts.append(f"Stage {i}: {s}.")
    facts.append(f"First stage: {steps[0]}.")
    facts.append(f"Final stage: {steps[-1]}.")
    return facts


def map_facts(d):
    facts = ["Before: " + "; ".join(d["before"]) + "."]
    for i, c in enumerate(d["changes"], 1):
        facts.append(f"Change {i}: {c}.")
    return facts


def facts_for(task_id, task):
    t = task["chart_type"]
    fn = {"line": line_facts, "bar": bar_facts, "pie": pie_facts,
          "table": table_facts, "process": process_facts, "map": map_facts}[t]
    return fn(task)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="train/eval/ielts_t1_structured.json")
    ap.add_argument("--id", default=None)
    args = ap.parse_args()
    d = json.load(open(args.data, encoding="utf-8"))["tasks"]
    ids = [args.id] if args.id else list(d)
    for tid in ids:
        print(f"## {tid} ({d[tid]['chart_type']})")
        for f in facts_for(tid, d[tid]):
            print(f"- {f}")
        print()


if __name__ == "__main__":
    main()
