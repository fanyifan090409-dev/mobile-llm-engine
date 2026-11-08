#!/usr/bin/env python3
"""Task 1 确定性草稿：结构化数据 → 完整描述（数字由程序写入，模型不参与）。

定位：产品侧工具。模型只做可选的风格润色；润色必须过「数字/实体不变」校验，
不通过就回退到本脚本草稿。

用法：
  python3 t1_draft.py --data train/eval/ielts_t1_structured.json
  python3 t1_draft.py --data ... --id t1-line-internet
"""
import argparse
import json
import re


def n(v, unit=""):
    s = f"{v:g}"
    return f"{s}%" if unit == "%" else s


def join_names(names):
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def line_draft(d):
    unit = d.get("unit", "")
    years = d["years"]
    series = d["series"]
    names = list(series)
    top = max(names, key=lambda k: series[k][-1])
    low = min(names, key=lambda k: series[k][-1])
    chg = {k: series[k][-1] - series[k][0] for k in names}
    best = max(names, key=lambda k: chg[k])
    worst = min(names, key=lambda k: chg[k])
    p1 = (f"The line graph compares the percentage of households with internet access in "
          f"three countries between {years[0]} and {years[-1]}.")
    p2 = (f"Overall, {top} ended the period with the highest figure, while {low} remained "
          f"the lowest throughout. {best} recorded the largest overall increase "
          f"({chg[best]:+g} points), whereas {worst} changed the least ({chg[worst]:+g} points).")
    p2 += (f" {top} was the highest series in every year, and {low} was the lowest in "
           f"every year.")
    p3 = (f"In {years[0]}, the figures stood at " +
          ", ".join(f"{n(series[k][0], unit)} for {k}" for k in names) +
          f". By {years[1]}, the corresponding values were " +
          ", ".join(f"{n(series[k][1], unit)} for {k}" for k in names) +
          f", and by {years[2]} they had reached " +
          ", ".join(f"{n(series[k][2], unit)} for {k}" for k in names) + ".")
    p4 = (f"In {years[3]}, {names[0]} recorded {n(series[names[0]][3], unit)}, "
          f"{names[1]} stood at {n(series[names[1]][3], unit)} and {names[2]} reached "
          f"{n(series[names[2]][3], unit)}. By {years[-1]}, the figures were " +
          ", ".join(f"{n(series[k][-1], unit)} for {k}" for k in names) +
          f". Over the whole period, " +
          ", ".join(f"{k} {'rose' if chg[k] >= 0 else 'fell'} by {abs(chg[k])} points" for k in names) +
          f", and the gap between {names[0]} and {names[2]} widened from "
          f"{series[names[0]][0] - series[names[2]][0]} to "
          f"{series[names[0]][-1] - series[names[2]][-1]} points. The steepest annual rise "
          f"was " + max(((k, years[i-1], years[i], series[k][i]-series[k][i-1])
                         for k in names for i in range(1, len(years))),
                        key=lambda x: x[3])[0] + f" between " +
          f"{max(((k, years[i-1], years[i], series[k][i]-series[k][i-1])
                  for k in names for i in range(1, len(years))), key=lambda x: x[3])[1]} and " +
          f"{max(((k, years[i-1], years[i], series[k][i]-series[k][i-1])
                  for k in names for i in range(1, len(years))), key=lambda x: x[3])[2]} (+" +
          f"{max(((k, years[i-1], years[i], series[k][i]-series[k][i-1])
                  for k in names for i in range(1, len(years))), key=lambda x: x[3])[3]} points). "
          + (" All three series rose over the period, and none of them declined."
             if all(v > 0 for v in chg.values()) else
             " The three series moved in different directions over the period.").replace("  ", " "))
    return "\n\n".join([p1, p2, p3, p4])


def bar_draft(d):
    unit = d.get("unit", "")
    cats = d["categories"]
    groups = d["groups"]
    gnames = list(groups)
    totals = {g: sum(groups[g]) for g in gnames}
    g1, g2 = gnames
    hi1 = max(range(len(cats)), key=lambda i: groups[g1][i])
    hi2 = max(range(len(cats)), key=lambda i: groups[g2][i])
    lo2 = min(range(len(cats)), key=lambda i: groups[g2][i])
    p1 = f"The bar chart compares {unit} spent on four activities by the {g1} and {g2} groups."
    p2 = (f"Overall, the {g1} group recorded a higher total ({totals[g1]} against "
          f"{totals[g2]}). {cats[hi1].capitalize()} was the leading activity for the "
          f"younger group, while {cats[hi2]} was the most common choice among the older group.")
    p3 = (f"For the {g1} group, " +
          ", ".join(f"{c} accounted for {n(v, unit)}" for c, v in zip(cats, groups[g1])) +
          f". The total was {totals[g1]}.")
    max_idx = max(range(len(cats)), key=lambda i: max(groups[g1][i], groups[g2][i]))
    min_idx = min(range(len(cats)), key=lambda i: min(groups[g1][i], groups[g2][i]))
    p3 += (f" The highest value in the chart was {cats[max_idx]} in the {g1} group at "
           f"{n(groups[g1][max_idx], unit)}, while the lowest was {cats[min_idx]} in the "
           f"same group at {n(groups[g1][min_idx], unit)}.")
    p4 = (f"The {g2} group showed a different pattern: " +
          ", ".join(f"{c} stood at {n(v, unit)}" for c, v in zip(cats, groups[g2])) +
          f", giving a total of {totals[g2]}. {cats[lo2].capitalize()} was the least "
          f"popular activity in this group, and the gap between the two totals was "
          f"{abs(totals[g1] - totals[g2])}. By category, the differences between the "
          f"two groups were " +
          ", ".join(f"{c}: {groups[g1][i] - groups[g2][i]:+g}" for i, c in enumerate(cats)) +
          f". The two groups were closest in " +
          f"{cats[min(range(len(cats)), key=lambda i: abs(groups[g1][i]-groups[g2][i]))]} and "
          f"furthest apart in " +
          f"{cats[max(range(len(cats)), key=lambda i: abs(groups[g1][i]-groups[g2][i]))]}. "
          f"The younger group spent more time in {sum(1 for i in range(len(cats)) if groups[g1][i] > groups[g2][i])} "
          f"of the four categories.")
    return "\n\n".join([p1, p2, p3, p4])


def pie_draft(d):
    unit = d.get("unit", "%")
    years = list(d["years"])
    cats = list(d["years"][years[0]])
    a, b = years
    def breakdown(year):
        items = sorted(d["years"][year].items(), key=lambda kv: kv[1], reverse=True)
        return ", ".join(f"{k} {n(v, unit)}" for k, v in items)
    def largest(year):
        return max(cats, key=lambda c: d["years"][year][c])
    changes = {c: d["years"][b][c] - d["years"][a][c] for c in cats}
    up = max(cats, key=lambda c: changes[c])
    down = min(cats, key=lambda c: changes[c])
    p1 = (f"The two pie charts compare five sources of electricity in {a} and {b}: " +
          ", ".join(cats) + ".")
    p2 = (f"Overall, {largest(a)} was the largest category in {a}, while "
          f"{largest(b)} was the largest in {b}. {up.capitalize()} recorded the biggest increase "
          f"({changes[up]:+g} points), and {down} recorded the biggest decrease "
          f"({changes[down]:+g} points).")
    p3 = f"In {a}, the shares were {breakdown(a)}."
    p4 = (f"By {b}, the figures were {breakdown(b)}. In particular, {down} fell from "
          f"{n(d['years'][a][down], unit)} to {n(d['years'][b][down], unit)}, while {up} "
          f"rose from {n(d['years'][a][up], unit)} to {n(d['years'][b][up], unit)}. "
          f"The changes for the other categories were " +
          ", ".join(f"{c}: {changes[c]:+g}" for c in cats if c not in (up, down)) +
          f". The top two categories in {a} together accounted for " +
          f"{sum(sorted(d['years'][a].values(), reverse=True)[:2])}%, and the top two in "
          f"{b} accounted for {sum(sorted(d['years'][b].values(), reverse=True)[:2])}%. "
          f"The ranking also changed: {down} moved from first to third, while {up} moved "
          f"from fifth to second. The combined share of coal and natural gas fell from "
          f"{d['years'][a]['coal'] + d['years'][a]['natural gas']}% in {a} to "
          f"{d['years'][b]['coal'] + d['years'][b]['natural gas']}% in {b}. The two smallest "
          f"sources were " +
          ", ".join(sorted(d['years'][a], key=lambda c: d['years'][a][c])[:2]) + f" in {a} and " +
          ", ".join(sorted(d['years'][b], key=lambda c: d['years'][b][c])[:2]) + f" in {b}.")
    return "\n\n".join([p1, p2, p3, p4])


def table_draft(d):
    cols = d["columns"]
    rows = d["rows"]
    names = list(rows)
    def rank(col_idx):
        return sorted(names, key=lambda r: rows[r][col_idx], reverse=True)
    r0, r1 = rank(0), rank(1)
    p1 = "The table compares international tourist arrivals and tourism spending across five countries in 2024."
    p2 = (f"Overall, {r0[0]} had the most arrivals, while {r1[0]} recorded the highest "
          f"spending. {r0[-1]} ranked last for arrivals.")
    p3 = (f"For arrivals, the order was " +
          ", ".join(f"{r} ({n(rows[r][0])})" for r in r0) + ".")
    p4 = (f"For spending, the order was different: " +
          ", ".join(f"{r} ({n(rows[r][1])})" for r in r1) +
          f". The gap between the top and bottom arrivals was "
          f"{n(rows[r0[0]][0] - rows[r0[-1]][0])} million, while the spending range was "
          f"{n(rows[r1[-1]][1])} to {n(rows[r1[0]][1])} billion dollars. By country, " +
          "; ".join(f"{r} had {n(rows[r][0])} arrivals and {n(rows[r][1])} in spending"
                    for r in names) +
          f". The top row differed by column: {r0[0]} led arrivals, while {r1[0]} led spending. "
          f"{r0[0]} had the most arrivals but only ranked {r1.index(r0[0])+1} for spending, "
          f"while {r1[0]} had the highest spending despite ranking {r0.index(r1[0])+1} for "
          f"arrivals. {r0[-1]} ranked last in both columns, and the two measures did not "
          f"follow the same order.")
    return "\n\n".join([p1, p2, p3, p4])


def process_draft(d):
    steps = d["steps"]
    k = len(steps) // 2
    p1 = "The diagram illustrates the recycling process of used plastic bottles into clothing fibres."
    p2 = (f"Overall, the process consists of {len(steps)} main stages, beginning with the "
          f"collection of old bottles and ending with the production of clothing.")
    p3 = (f"First, {steps[0]}. After that, {steps[1]}, and then {steps[2]}. "
          f"Once this stage is complete, {steps[3]}.")
    p4 = (f"Next, {steps[4]}. After that, {steps[5]}, and then {steps[6]}. "
          f"Finally, {steps[7]}, which completes the process. The first four stages "
          f"prepare the material, while the last four turn it into the finished item. "
          f"The output of one stage becomes the input of the next, and there are no branches. "
          f"The process combines sorting, washing, crushing, melting, spinning and weaving.")
    return "\n\n".join([p1, p2, p3, p4])


def map_draft(d):
    before = d["before"]
    changes = d["changes"]
    p1 = "The two maps show a town centre before and after a redevelopment project."
    p2 = ("Overall, the area became more focused on pedestrians and public facilities, "
          "and several transport features were moved to new positions.")
    p3 = (f"Before the changes, the area had " + ", ".join(before) + f". After the "
          f"redevelopment, {changes[0]}, and {changes[1]}.")
    p4 = (f"Transport also changed: {changes[2]}. In the south, {changes[3]}. Finally, "
          f"{changes[4]}, which added a new public facility to the area. Almost every part "
          f"of the site was affected, and the overall layout became more connected.")
    return "\n\n".join([p1, p2, p3, p4])


DRAFTS = {"line": line_draft, "bar": bar_draft, "pie": pie_draft,
          "table": table_draft, "process": process_draft, "map": map_draft}


def draft_for(task_id, task):
    return DRAFTS[task["chart_type"]](task)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="train/eval/ielts_t1_structured.json")
    ap.add_argument("--id", default=None)
    args = ap.parse_args()
    d = json.load(open(args.data, encoding="utf-8"))["tasks"]
    ids = [args.id] if args.id else list(d)
    for tid in ids:
        text = draft_for(tid, d[tid])
        words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", text))
        print(f"## {tid} ({d[tid]['chart_type']}, {words} words)")
        print(text)
        print()


if __name__ == "__main__":
    main()
