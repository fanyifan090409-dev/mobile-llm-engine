#!/usr/bin/env python3
"""SFT20b 日期数据独立反解复核：不信生成逻辑，从用户话术重新推算目标时间。"""
import json
import re
import sys
from datetime import date, timedelta

CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
      "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
DATE_RE = re.compile(
    r"(今天|明天|后天|大后天|本周[一二三四五六日]|这周[一二三四五六日]|下周[一二三四五六日]"
    r"|下下周[一二三四五六日]|\d+天后|\d{1,2}月\d{1,2}[日号]|下个月\d{1,2}号|今晚|明早|明晚)(.*)$")
TIME_RE = re.compile(
    r"^(凌晨|早上|上午|中午|下午|傍晚|晚上)?(十二|十一|十|九|八|七|六|五|四|三|两|二|一)点"
    r"(?:(半)|(一刻)|(三刻)|(\d+)分)?")


def next_week(today, wd):
    return today - timedelta(days=today.weekday()) + timedelta(days=7 + wd)


def this_week(today, wd):
    return today - timedelta(days=today.weekday()) + timedelta(days=wd)


def parse_time(period, hour_cn, half, q1, q3, mins, combined):
    h = CN[hour_cn]
    if period is None:
        period = "晚上" if combined in ("今晚", "明晚") else "早上"
    if period == "凌晨":
        h = 0 if h == 12 else h
    elif period == "中午":
        h = 12 if h == 12 else h + 12
    elif period in ("下午", "傍晚"):
        h = h if h == 12 else h + 12
    elif period == "晚上":
        h = 0 if h == 12 else (h + 12 if h < 12 else h)
    m = 30 if half else 15 if q1 else 45 if q3 else int(mins) if mins else 0
    return h, m


def expected(user):
    today = date(*map(int, re.search(r"今天是(\d{4})年(\d{2})月(\d{2})日。", user).groups()))
    body = user.split("，", 1)[1]
    expr, rest = DATE_RE.search(body).groups()
    tm = TIME_RE.match(rest)
    assert tm, (user, rest)
    h, mi = parse_time(tm.group(1), tm.group(2), tm.group(3), tm.group(4), tm.group(5), tm.group(6), expr)
    if expr in ("今天", "今晚"):
        d = today
    elif expr in ("明天", "明晚", "明早"):
        d = today + timedelta(days=1)
    elif expr == "后天":
        d = today + timedelta(days=2)
    elif expr == "大后天":
        d = today + timedelta(days=3)
    elif expr.startswith("下下周"):
        d = next_week(today, "一二三四五六日".index(expr[-1])) + timedelta(days=7)
    elif expr.startswith("下周"):
        d = next_week(today, "一二三四五六日".index(expr[-1]))
    elif expr.startswith(("本周", "这周")):
        d = this_week(today, "一二三四五六日".index(expr[-1]))
    elif expr.endswith("天后"):
        d = today + timedelta(days=int(expr[:-2]))
    elif expr.startswith("下个月"):
        day = int(re.search(r"\d+", expr).group())
        y = today.year + (1 if today.month == 12 else 0)
        mo = 1 if today.month == 12 else today.month + 1
        d = date(y, mo, day)
    else:
        mo, day = map(int, re.match(r"(\d{1,2})月(\d{1,2})", expr).groups())
        y = today.year
        while True:
            try:
                d = date(y, mo, day)
                break
            except ValueError:  # 2月29日在平年不存在，顺延到下一个闰年
                y += 1
        if d < today:
            y += 1
            while True:
                try:
                    d = date(y, mo, day)
                    break
                except ValueError:
                    y += 1
    return d, h, mi


def check(path):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    total = bad = 0
    errors = []
    for r in rows:
        if r.get("source") != "rule":
            continue
        u = r["messages"][1]["content"]
        args = json.loads(re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
                                    r["messages"][2]["content"], re.S).group(1))["arguments"]
        d, h, mi = expected(u)
        key = "start_time" if "start_time" in args else "remind_time"
        want = f"{d.isoformat()} {h:02d}:{mi:02d}"
        total += 1
        if args[key] != want:
            bad += 1
            errors.append((u, args[key], want))
    return total, bad, errors


if __name__ == "__main__":
    for p in sys.argv[1:] or ["train/synthesize/date_sft20b/train.jsonl",
                              "train/synthesize/date_sft20b/val.jsonl"]:
        total, bad, errors = check(p)
        print(f"{p}: rule 样本 {total}，错误 {bad}")
        for e in errors[:10]:
            print("  ", e)
        if bad:
            sys.exit(1)
