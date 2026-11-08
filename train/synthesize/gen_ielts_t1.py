#!/usr/bin/env python3
"""雅思 Task 1 读图专项数据生成（SFT24 单点验证用）。

设计原则：
- 所有数字由数据表生成，范文逐项引用，杜绝「年份错位/趋势读反/合计当各自」；
- 六类图形（折线/柱状/饼图/表格/流程/地图）各 1/6，共 800 条；
- prompt 与 train/eval/ielts_writing_eval.json 同一措辞，避免训练/评测分布漂移；
- 输出 messages 格式，与 data/sft19/ielts.jsonl 一致。

用法：python3 gen_ielts_t1.py --n 800 --out train/synthesize/ielts_t1_sft24.jsonl
"""
import argparse
import json
import random
import re

BANNED = ["delve", "pivotal", "paramount", "multifaceted", "tapestry",
          "double-edged sword", "It is widely acknowledged", "In today's society"]


def prompt_wrap(chart_type, question, data_desc):
    return (f"雅思写作 Task 1（{chart_type}）。题目：{question}\n"
            f"数据（{data_desc}）\n"
            f"请用英文写一篇 150 词以上的回答。要求：以亚洲考生真人风格写作，"
            f"目标 band 7.0-7.5，不背模板、不堆砌生僻词、不出现 AI 腔；结构自然，论证具体。")


def order_desc(vals):
    return sorted(range(len(vals)), key=lambda i: vals[i], reverse=True)


def cap(text):
    return text[0].upper() + text[1:] if text else text


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def mv(v):
    if v > 0:
        return f"rose by {v}"
    if v < 0:
        return f"fell by {abs(v)}"
    return "stayed flat"


# ---------------- 折线图 ----------------
LINE_METRICS = [
    "the percentage of households with internet access",
    "the share of electricity generated from renewable sources",
    "the proportion of commuters using public transport",
    "the percentage of adults taking part in regular exercise",
]


def gen_line(rng):
    metric = rng.choice(LINE_METRICS)
    start = rng.choice([1990, 1995, 2000, 2005])
    years = [start + 5 * i for i in range(5)]
    series = {}
    for name in ("A", "B"):
        base = rng.randint(4, 30)
        vals = [base]
        style = rng.choice(["rise", "rise_fast", "plateau", "flat"])
        for i in range(4):
            if style == "rise":
                vals.append(min(96, vals[-1] + rng.randint(7, 18)))
            elif style == "rise_fast":
                vals.append(min(96, vals[-1] + rng.randint(14, 26)))
            elif style == "plateau":
                vals.append(vals[-1] if i >= 2 else min(96, vals[-1] + rng.randint(10, 20)))
            elif style == "dip":
                vals.append(max(2, vals[-1] - rng.randint(4, 12)) if i == 1 else min(96, vals[-1] + rng.randint(6, 15)))
            else:
                vals.append(max(2, min(96, vals[-1] + rng.randint(-3, 3))))
        series[name] = vals
    # C 国始终最低，避免范文写出与数据矛盾的「垫底」判断
    series["C"] = [max(1, min(series["A"][i], series["B"][i]) - rng.randint(1, 5)) for i in range(5)]
    data_desc = "占比：" + "；".join(
        f"{y} 年 " + "/".join(f"{k} 国 {series[k][i]}%" for k in "ABC")
        for i, y in enumerate(years)
    )
    question = (f"The line graph below shows {metric} in three countries between "
                f"{years[0]} and {years[-1]}. Summarise the information by selecting and "
                f"reporting the main features, and make comparisons where relevant.")

    top = max("ABC", key=lambda k: series[k][-1])
    fastest = max("ABC", key=lambda k: series[k][-1] - series[k][0])
    chg = {k: series[k][-1] - series[k][0] for k in "ABC"}
    gap0 = series["A"][0] - series["C"][0]
    gap2 = series["A"][2] - series["C"][2]
    if gap2 > gap0:
        gap_phrase = f"widened from {gap0} to {gap2}"
    elif gap2 < gap0:
        gap_phrase = f"narrowed from {gap0} to {gap2}"
    else:
        gap_phrase = f"remained at {gap0}"
    p1 = (f"The line graph compares {metric} across three countries between "
          f"{years[0]} and {years[-1]}.")
    p2 = (f"Overall, {top} ended the period with the highest figure, while C stayed "
          f"at the bottom throughout. {fastest} recorded the most noticeable growth.")
    overtake = None
    for i in range(1, 5):
        for x, y in (("A", "B"), ("B", "A")):
            if series[x][i - 1] < series[y][i - 1] and series[x][i] > series[y][i]:
                overtake = (x, y, years[i])
    if overtake:
        p2 += f" {overtake[0]} also overtook {overtake[1]} in {overtake[2]}."
    else:
        p2 += " The three lines never cross, so the ranking stays the same."
    body1 = (f"In {years[0]}, the figures stood at {series['A'][0]}% for A, "
             f"{series['B'][0]}% for B and {series['C'][0]}% for C, so A and B were "
             f"already {abs(series['A'][0] - series['B'][0])} points apart. Five years "
             f"later, A had risen to {series['A'][1]}%, B stood at {series['B'][1]}% and "
             f"C reached {series['C'][1]}%. By {years[2]}, the corresponding figures were "
             f"{series['A'][2]}%, {series['B'][2]}% and {series['C'][2]}%, so the gap "
             f"between A and C {gap_phrase} percentage points. C "
             f"remained below both A and B at every point.")
    body2 = (f"The three series moved at different speeds. In {years[3]}, A recorded "
             f"{series['A'][3]}%, compared with {series['B'][3]}% in B and "
             f"{series['C'][3]}% in C; by {years[4]}, the three countries reached "
             f"{series['A'][4]}%, {series['B'][4]}% and {series['C'][4]}% respectively. "
             f"Over the whole period, A {'rose' if chg['A'] >= 0 else 'fell'} by "
             f"{abs(chg['A'])} percentage points, B {'rose' if chg['B'] >= 0 else 'fell'} "
             f"by {abs(chg['B'])} and C {'rose' if chg['C'] >= 0 else 'fell'} by "
             f"{abs(chg['C'])}. Between {years[2]} and {years[4]}, A "
             f"{mv(series['A'][4] - series['A'][2])} points, B "
             f"{mv(series['B'][4] - series['B'][2])} and C "
             f"{mv(series['C'][4] - series['C'][2])}.")
    essay = "\n\n".join([p1, p2, body1, body2])
    derived = {gap0, gap2, abs(chg["A"]), abs(chg["B"]), abs(chg["C"]),
               abs(series["A"][0] - series["B"][0]),
               abs(series["A"][4] - series["A"][2]),
               abs(series["B"][4] - series["B"][2]),
               abs(series["C"][4] - series["C"][2])}
    return "line graph", question, data_desc, essay, derived


# ---------------- 柱状图 ----------------
BAR_SETS = [
    ("average weekly hours spent on four leisure activities",
     ["reading", "sport", "streaming", "socialising"], ["18-30", "45-60"]),
    ("monthly spending on four categories",
     ["food", "transport", "housing", "entertainment"], ["2015", "2025"]),
    ("the number of visits to four types of attraction",
     ["museum visits", "park visits", "cinema visits", "gallery visits"], ["locals", "tourists"]),
]


def gen_bar(rng):
    topic, cats, groups = rng.choice(BAR_SETS)
    vals = {g: [rng.randint(2, 20) for _ in cats] for g in groups}
    g1, g2 = groups
    hi1 = order_desc(vals[g1])
    hi2 = order_desc(vals[g2])
    lo2 = hi2[-1]
    total1, total2 = sum(vals[g1]), sum(vals[g2])
    data_desc = "；".join(
        f"{g}——" + "、".join(f"{c} {v}" for c, v in zip(cats, vals[g]))
        for g in groups
    )
    question = (f"The bar chart below shows {topic} for two groups. Summarise the "
                f"information by selecting and reporting the main features, and make "
                f"comparisons where relevant.")
    diff_idx = max(range(4), key=lambda i: abs(vals[g1][i] - vals[g2][i]))
    p1 = f"The bar chart compares {topic} between {g1} and {g2}."
    p2 = (f"Overall, {g1} recorded a higher total ({total1} against {total2}), and "
          f"the {cats[hi1[0]]} category was the largest in that group, whereas "
          f"the {cats[hi2[0]]} category was the most common choice among {g2}.")
    second_phrase = ("tied with" if vals[g1][hi1[1]] == vals[g1][hi1[0]] else "followed by")
    lead_gap = vals[g1][hi1[0]] - vals[g1][hi1[1]]
    gap34 = vals[g1][hi1[2]] - vals[g1][hi1[3]]
    tail = "level with each other" if gap34 == 0 else f"only {gap34} apart"
    body1 = (f"For {g1}, the {cats[hi1[0]]} category accounted for {vals[g1][hi1[0]]}, "
             f"{second_phrase} the {cats[hi1[1]]} category at {vals[g1][hi1[1]]}. The other two categories were "
             f"closer, with the {cats[hi1[2]]} category at {vals[g1][hi1[2]]} and the {cats[hi1[3]]} category at "
             f"{vals[g1][hi1[3]]}, {tail}. The "
             f"{'' if lead_gap == 0 else 'leading category was ' + str(lead_gap) + ' points ahead of the second. '}"
             f"The four categories together produced a total of "
             f"{total1}, and the gap between the largest and smallest was "
             f"{vals[g1][hi1[0]] - vals[g1][hi1[-1]]}.")
    lower_count = sum(1 for i in range(4) if vals[g2][i] < vals[g1][i])
    close_idx = min(range(4), key=lambda i: abs(vals[g1][i] - vals[g2][i]))
    body2 = (f"The pattern for {g2} was different. The {cats[hi2[0]]} category led with "
             f"{vals[g2][hi2[0]]}, followed by the {cats[hi2[1]]} category at {vals[g2][hi2[1]]}, "
             f"while the {cats[lo2]} category was the least popular at {vals[g2][lo2]}. Across the "
             f"four categories, the figures for {g2} were lower than those for {g1} in "
             f"{lower_count} of them. "
             f"The clearest difference appeared in the {cats[diff_idx]} category, where the two "
             f"groups recorded {vals[g1][diff_idx]} and {vals[g2][diff_idx]}. The "
             f"difference between the two totals was {abs(total1 - total2)}. The two "
             f"groups were closest in the {cats[close_idx]} category, at {vals[g1][close_idx]} and "
             f"{vals[g2][close_idx]} respectively. The largest category in {g2} was "
             f"{vals[g2][hi2[0]] - vals[g2][hi2[-1]]} points above its smallest.")
    essay = "\n\n".join([p1, p2, body1, body2])
    derived = {total1, total2, abs(vals[g1][diff_idx] - vals[g2][diff_idx]),
               abs(total1 - total2), lower_count, abs(vals[g1][close_idx] - vals[g2][close_idx]),
               vals[g1][hi1[0]] - vals[g1][hi1[-1]],
               vals[g2][hi2[0]] - vals[g2][hi2[-1]],
               vals[g1][hi1[2]] - vals[g1][hi1[3]],
               vals[g1][hi1[0]] - vals[g1][hi1[1]]}
    return "bar chart", question, data_desc, essay, derived


# ---------------- 饼图 ----------------
PIE_SETS = [
    ("the sources of electricity in one country",
     ["coal", "natural gas", "nuclear", "hydropower", "solar and wind"]),
    ("household expenditure in one city",
     ["housing", "food", "transport", "education", "other items"]),
    ("the reasons why people moved to a city",
     ["work", "study", "family", "housing", "other reasons"]),
]


def split_100(rng, k):
    cuts = sorted(rng.sample(range(5, 96), k - 1))
    parts = [cuts[0]] + [cuts[i] - cuts[i - 1] for i in range(1, k - 1)] + [100 - cuts[-1]]
    return parts


def gen_pie(rng):
    topic, cats = rng.choice(PIE_SETS)
    y1, y2 = rng.choice([(2005, 2025), (2010, 2020), (2000, 2020)])
    a = split_100(rng, 5)
    b = split_100(rng, 5)
    i, j = rng.sample(range(5), 2)
    delta = rng.randint(6, 14)
    if b[i] - delta < 3:
        delta = b[i] - 3
    b[i] -= delta
    b[j] += delta
    data_desc = (f"{y1} 年——" + "、".join(f"{c} {v}%" for c, v in zip(cats, a)) +
                 f"；{y2} 年——" + "、".join(f"{c} {v}%" for c, v in zip(cats, b)))
    question = (f"The two pie charts below show {topic} in {y1} and {y2}. Summarise "
                f"the information by selecting and reporting the main features, and "
                f"make comparisons where relevant.")
    o1, o2 = order_desc(a), order_desc(b)
    shift_cat = max(range(5), key=lambda k: abs(b[k] - a[k]))
    delta_i = abs(b[shift_cat] - a[shift_cat])
    p1 = f"The two pie charts compare {topic} in {y1} and {y2}."
    if o1[0] == o2[0]:
        lead = f"{cap(cats[o1[0]])} remained the largest category in both years"
    else:
        lead = (f"{cap(cats[o1[0]])} was the largest category in {y1}, but {cats[o2[0]]} "
                f"had become the biggest by {y2}")
    p2 = (f"Overall, {lead}. The clearest change was in {cats[shift_cat]}, which "
          f"{'rose' if b[shift_cat] > a[shift_cat] else 'fell'} by {delta_i} percentage "
          f"points, a larger shift than in any other category.")
    body1 = (f"In {y1}, {cap(cats[o1[0]])} made up {a[o1[0]]}% of the total, followed by "
             f"{cats[o1[1]]} at {a[o1[1]]}%. The remaining shares were {a[o1[2]]}% for "
             f"{cats[o1[2]]}, {a[o1[3]]}% for {cats[o1[3]]} and {a[o1[4]]}% for "
             f"{cats[o1[4]]}, only {a[o1[3]] - a[o1[4]]} points below {cats[o1[3]]}. "
             f"The top two categories together accounted for "
             f"{a[o1[0]] + a[o1[1]]}% of the total, while {cats[o1[4]]} was the smallest "
             f"at {a[o1[4]]}%.")
    body2 = (f"By {y2}, the balance had shifted. {cap(cats[o2[0]])} had reached {b[o2[0]]}% "
             f"and {cats[o2[1]]} stood at {b[o2[1]]}%. The other three categories "
             f"accounted for {b[o2[2]]}%, {b[o2[3]]}% and {b[o2[4]]}% respectively. "
             f"In particular, {cats[i]} {'rose' if b[i] > a[i] else 'fell'} from {a[i]}% "
             f"to {b[i]}%, while {cats[j]} {'rose' if b[j] > a[j] else 'fell'} from "
             f"{a[j]}% to {b[j]}%, which changed the overall ranking of the categories. Across the five categories, the largest increase was "
             f"{max(b[k]-a[k] for k in range(5))} points and the largest decrease was "
             f"{abs(min(b[k]-a[k] for k in range(5)))} points. The smallest category "
             f"in {y2} was {cats[o2[4]]} at {b[o2[4]]}%. The share of {cats[o2[2]]} "
             f"stood at {b[o2[2]]}%, compared with {a[o2[2]]}% in {y1}.")
    essay = "\n\n".join([p1, p2, body1, body2])
    derived = {delta_i, abs(a[i] - b[i]), abs(a[j] - b[j]),
               abs(max(b[k]-a[k] for k in range(5))),
               abs(min(b[k]-a[k] for k in range(5))),
               a[o1[0]] + a[o1[1]], a[o1[3]] - a[o1[4]],
               abs(b[o2[2]] - a[o2[2]])}
    return "pie charts", question, data_desc, essay, derived


# ---------------- 表格 ----------------
TABLE_SETS = [
    ("international tourist arrivals and tourism spending",
     ["France", "Spain", "the United States", "China", "Japan"],
     ["arrivals", "spending"], "2024"),
    ("student and teacher numbers",
     ["North", "South", "East", "West", "Central"],
     ["students", "teachers"], "2025"),
]


def gen_table(rng):
    topic, rows, cols, year = rng.choice(TABLE_SETS)
    v1 = rng.sample(range(20, 100, 5), 5)
    v2 = rng.sample(range(30, 140, 10), 5)
    data_desc = f"{year} 年：" + "；".join(
        f"{r}——{cols[0]} {v1[i]}、{cols[1]} {v2[i]}" for i, r in enumerate(rows)
    )
    question = (f"The table below shows {topic} in five places in {year}. Summarise "
                f"the information by selecting and reporting the main features, and "
                f"make comparisons where relevant.")
    o1, o2 = order_desc(v1), order_desc(v2)
    gap = v1[o1[0]] - v1[o1[-1]]
    rank_o2_top_in_o1 = o1.index(o2[0]) + 1
    p1 = f"The table compares {topic} across five places in {year}."
    p2 = (f"Overall, {rows[o1[0]]} had the most {cols[0]}, while {rows[o2[0]]} had the "
          f"most {cols[1]}. {rows[o1[-1]]} ranked last for {cols[0]}.")
    body1 = (f"{rows[o1[0]]} recorded {v1[o1[0]]} {cols[0]}, ahead of {rows[o1[1]]} "
             f"at {v1[o1[1]]} and {rows[o1[2]]} at {v1[o1[2]]}. The two lowest figures "
             f"belonged to {rows[o1[3]]} and {rows[o1[4]]}, at {v1[o1[3]]} and "
             f"{v1[o1[4]]}. The gap between the top and bottom places was {gap}, so "
             f"the first measure ranged from {v1[o1[-1]]} to {v1[o1[0]]}. The second "
             f"and third places were separated by only {v1[o1[1]] - v1[o1[2]]}, and the "
             f"top two were {v1[o1[0]] - v1[o1[1]]} apart.")
    body2 = (f"For {cols[1]}, the order was different. {rows[o2[0]]} led with "
             f"{v2[o2[0]]}, followed by {rows[o2[1]]} at {v2[o2[1]]}. The remaining "
             f"three recorded {v2[o2[2]]}, {v2[o2[3]]} and {v2[o2[4]]} respectively. "
             f"Notably, {rows[o2[0]]} ranked only {ordinal(rank_o2_top_in_o1)} for {cols[0]}, "
             f"so the two measures did not follow the same order. The range in the "
             f"second column was {v2[o2[0]] - v2[o2[-1]]}, from {v2[o2[-1]]} to "
             f"{v2[o2[0]]}. The top two in this column were {v2[o2[0]] - v2[o2[1]]} apart, "
             f"and the next two were separated by {v2[o2[1]] - v2[o2[2]]}. The bottom "
             f"two recorded {v2[o2[-2]]} and {v2[o2[-1]]}, a difference of "
             f"{v2[o2[-2]] - v2[o2[-1]]}.")
    essay = "\n\n".join([p1, p2, body1, body2])
    derived = {gap, rank_o2_top_in_o1, v2[o2[0]] - v2[o2[-1]], v2[o2[0]] - v2[o2[1]],
               v1[o1[1]] - v1[o1[2]], v2[o2[1]] - v2[o2[2]],
               v1[o1[0]] - v1[o1[1]], v2[o2[-2]] - v2[o2[-1]]}
    return "table", question, data_desc, essay, derived


# ---------------- 流程图 ----------------
PROCESSES = [
    ("how used plastic bottles are recycled and turned into clothing fibres",
     ["old bottles are collected from recycling bins",
      "the bottles are transported to a sorting plant",
      "they are sorted by colour and plastic type",
      "the sorted bottles are washed and their labels removed",
      "the bottles are crushed into thin flakes",
      "the flakes are melted into granules",
      "the granules are spun into fibres",
      "the fibres are woven into clothing"]),
    ("how glass is recycled",
     ["used glass is collected from bottle banks",
      "the glass is taken to a treatment plant",
      "it is washed to remove dirt and labels",
      "the glass is crushed into small pieces",
      "the pieces are melted in a furnace",
      "the molten glass is poured into moulds",
      "new bottles are formed and cooled"]),
    ("how drinking water is treated",
     ["water is pumped from a river",
      "it passes through a screen to remove large objects",
      "chemicals are added to make particles settle",
      "the water is filtered through sand",
      "it is disinfected with chlorine",
      "the treated water is stored in tanks",
      "it is pumped to homes"]),
    ("how tea is produced",
     ["tea leaves are picked by hand",
      "the leaves are spread out to wither",
      "they are rolled to release flavour",
      "the leaves are fermented",
      "they are dried in an oven",
      "the dried leaves are sorted by grade",
      "the tea is packed and shipped"]),
]


def gen_process(rng):
    topic, steps = rng.choice(PROCESSES)
    data_desc = "流程：" + "；".join(f"{i+1}) {s}" for i, s in enumerate(steps))
    question = (f"The diagram below shows {topic}. Summarise the information by "
                f"selecting and reporting the main features.")
    n = len(steps)
    p1 = f"The diagram illustrates {topic}."
    p2 = (f"Overall, the process consists of {n} main stages, beginning with the "
          f"collection of raw materials and ending with a finished product ready for use. "
          f"Each stage depends on the previous one, so the material moves through the "
          f"system in a fixed order.")
    body1 = (f"First, {steps[0]}. After that, {steps[1]}, and then {steps[2]}. "
             f"Once this stage is complete, {steps[3]}.")
    rest = steps[4:-1]
    body2 = "Next, " + rest[0] + "."
    for st in rest[1:]:
        body2 += f" After that, {st}."
    body2 += (f" Finally, {steps[-1]}, which completes the process. The early stages "
              f"focus on collecting and preparing the material, while the later ones "
              f"shape it into the final product. The whole sequence is continuous, and "
              f"the output of one stage becomes the input of the next. The diagram "
              f"shows no branches, so the process follows a single linear path.")
    essay = "\n\n".join([p1, p2, body1, body2])
    derived = set()
    return "process diagram", question, data_desc, essay, derived


# ---------------- 地图 ----------------
MAP_SETS = [
    ("a town centre before and after a redevelopment project",
     "the centre had a market square, a small car park in the east, a bus stop in the north and a narrow shopping street in the south, with few trees",
     ["the market square in the centre became a pedestrian area",
      "the car park in the east was replaced by a garden",
      "the bus stop moved from the north side to the north-east corner",
      "the narrow shopping street in the south was widened and given trees and cycle lanes",
      "a new library was built in the west"]),
    ("a coastal village before and after a new harbour was built",
     "the village had fishing huts in the south, a beach in the east, a road along the north coast and a car park in the west",
     ["the fishing huts in the south were replaced by a hotel",
      "the beach in the east was extended",
      "the road along the north coast was widened",
      "a new marina was built next to the harbour",
      "the car park in the west was moved inland"]),
    ("a university campus before and after expansion",
     "the campus had a playing field in the north, a car park in the east, a main road in the south and a garden in the centre",
     ["the playing field in the north was replaced by a library",
      "the car park in the east was turned into student housing",
      "the main road in the south was closed to traffic",
      "a new sports centre was added in the west",
      "the garden in the centre was enlarged"]),
]


def gen_map(rng):
    topic, before, changes = rng.choice(MAP_SETS)
    data_desc = f"改造前：{before}；改造后：" + "；".join(changes)
    question = (f"The two maps below show {topic}. Summarise the information by "
                f"selecting and reporting the main features, and make comparisons where relevant.")
    p1 = f"The two maps show {topic}."
    p2 = ("Overall, the area became more developed and its transport features were "
          "reorganised. Several older facilities were replaced, while new ones were "
          "added in different positions. The road network was also adjusted to serve "
          "the new layout.")
    body1 = (f"Before the changes, {before}. After the redevelopment, {changes[0]}, "
             f"and {changes[1]}.")
    body2 = (f"Transport also changed. {changes[2][0].upper() + changes[2][1:]}. "
             f"In addition, {changes[3]}. Finally, {changes[4]}. Taken together, these "
             f"changes made the area more connected and more focused on public use. "
          f"Almost every part of the site was affected in some way.")
    essay = "\n\n".join([p1, p2, body1, body2])
    derived = set()
    return "map", question, data_desc, essay, derived


GENS = [gen_line, gen_bar, gen_pie, gen_table, gen_process, gen_map]


def fix_plural(essay):
    essay = re.sub(r"\b1 points\b", "1 point", essay)
    essay = re.sub(r"\b1 percentage points\b", "1 percentage point", essay)
    return essay


def qc(essay, data_desc, question, derived=()):
    words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", essay))
    errs = []
    if not (150 <= words <= 300):
        errs.append(f"word_count={words}")
    low = essay.lower()
    for b in BANNED:
        if b.lower() in low:
            errs.append(f"banned={b}")
    allowed = set(re.findall(r"\d+", data_desc + " " + question)) | {str(d) for d in derived}
    used = set(re.findall(r"\d+", essay))
    extra = used - allowed
    if extra:
        errs.append("numbers_not_in_data=" + ",".join(sorted(extra)))
    if len([p for p in essay.split("\n\n") if p.strip()]) < 3:
        errs.append("paragraphs<3")
    return words, errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seed", type=int, default=20261108)
    ap.add_argument("--out", default="train/synthesize/ielts_t1_sft24.jsonl")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    target = args.n // len(GENS)
    rows, bad = [], 0
    for gen in GENS:
        made, attempts = 0, 0
        while made < target and attempts < target * 30:
            attempts += 1
            chart_type, question, data_desc, essay, derived = gen(rng)
            essay = fix_plural(essay)
            words, errs = qc(essay, data_desc, question, derived)
            if errs:
                bad += 1
                continue
            rows.append({"messages": [
                {"role": "user", "content": prompt_wrap(chart_type, question, data_desc)},
                {"role": "assistant", "content": essay},
            ]})
            made += 1
        print(f"{gen.__name__}: {made}/{target}")
    rng.shuffle(rows)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"WROTE {len(rows)} / {args.n} (qc_rejected={bad}) -> {args.out}")


if __name__ == "__main__":
    main()
