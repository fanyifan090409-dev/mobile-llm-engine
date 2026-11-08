#!/usr/bin/env python3
"""SFT21b 数据：修复 SFT21 过度反问。

SFT21 复盘：clarify 1,000 / 派单 1,500 / 4 epochs → 模糊 16/20 但派单 0/11、数学 53.6%。
本版：
  clarify 600（分层抽样，占比 ~18%）
  dispatch 2,000 单轮（SFT20 领队轨迹截到 system+user+首个派单，过滤模糊指令）
  dispatch 300 多轮（保留工具结果后的汇总行为）
  chat 400
合计 3,300，训练 3 epochs。
"""
import json
import os
import random
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "train/synthesize/cloud_sft20/leader_sft20.jsonl")
CLARIFY_DIR = os.path.join(ROOT, "train/synthesize/clarify_sft21")
OUTDIR = os.path.join(ROOT, "train/synthesize/clarify_sft21b")
random.seed(20261108)

TIME_RE = re.compile(r"今天|明天|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
                     r"下个?月|\d{1,2}\s*月\s*\d{1,2}\s*[日号]|\d{1,2}\s*[点时]|"
                     r"上午|下午|晚上|中午|早上|傍晚|月底|月初")
AMBIG_RE = re.compile(r"具体时间我发你|时间还没定|回头再说|看房|夜跑|那个会|刚才那个|"
                      r"帮我约个事|帮我安排一下$|提醒我一下")

rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
SYSTEM = next(m["content"] for m in rows[0]["messages"] if m["role"] == "system")


def dispatch_like(user, task_type):
    if AMBIG_RE.search(user):
        return False
    if task_type in ("calendar", "reminder"):
        return bool(TIME_RE.search(user))
    if task_type == "translate":
        return "翻译" in user
    if task_type == "summary":
        return any(k in user for k in ("总结", "摘要", "缩成", "概括", "压缩"))
    if task_type == "mixed":
        return bool(TIME_RE.search(user)) and ("翻译" in user or "总结" in user)
    return False


def first_dispatch(r):
    """截到首个派单回合（system+user+assistant），assistant 必须含工具调用。"""
    msgs = r["messages"]
    if len(msgs) < 3:
        return None
    if "<tool_call>" not in msgs[2].get("content", ""):
        return None
    return {"role": "leader", "task_type": r.get("task_type"),
            "messages": [msgs[0], msgs[1], msgs[2]]}


def gen_synthetic_dispatch():
    """补单轮清晰派单：每条都带明确时间/内容，assistant 只发一个 dispatch 工具调用。"""
    events = ["牙医复诊", "家长会", "吉他课", "项目评审", "体检", "面试", "同学聚餐",
              "钢琴课", "篮球训练", "英语角", "志愿者活动", "期末复习", "看牙", "理发"]
    times = ["明天下午三点", "后天上午十点", "这周六下午两点", "下周一早上八点半",
             "下周三晚上七点", "11月12日上午九点", "周五中午十二点", "下周二傍晚六点",
             "本周四下午四点", "下个月3号上午十一点", "明天晚上八点", "后天下午四点半"]
    places = ["口腔医院", "学校", "公司会议室", "家", "商场三楼", "社区中心", "图书馆", "健身房"]
    remind = ["吃药", "交作业", "给妈妈打电话", "取快递", "交报告", "打卡", "喝水", "浇花",
              "背单词", "复习微积分", "交房租", "预约体检"]
    texts = ["我明天不能参加会议，请帮我请假。", "会议改到周五下午三点。",
             "本周的作业已经提交，请查收。", "请确认周五之前能完成报告。",
             "明天下午的航班延误了两个小时。"]
    summaries = [
        "马拉松志愿服务落地滨江赛道，牵头人提前一周拉了任务清单，把物料、人员和动线逐项过了一遍。整场花费1500元，对账后结余110元。",
        "公司第三季度营收同比增长18%，主要来自海外市场。毛利率从32%提升到35%，但研发费用增加了两成。",
        "小组作业一共三个人，分别负责资料、建模和展示。周三前交初稿，周五合并，下周一课堂汇报。",
        "这次实验用了两组样本，每组二十个数据。第一组均值偏高，第二组波动更大，需要再补一次对照实验。",
    ]
    out = []
    for i in range(700):
        if i % 2 == 0:
            ev = random.choice(events)
            tm = random.choice(times)
            pl = random.choice(places)
            user = f"帮我安排{ev}，{tm}，地点在{pl}。"
            task = f"添加日历事件：{ev}，{tm}，地点在{pl}。今天是2026年11月08日。"
            worker = "calendar_worker"
        else:
            rc = random.choice(remind)
            tm = random.choice(times)
            user = f"提醒我{rc}，{tm}。"
            task = f"设置提醒：{rc}，{tm}。今天是2026年11月08日。"
            worker = "reminder_worker"
        call = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                f'"worker": "{worker}", "task": "{task}"' + '}}\n</tool_call>')
        out.append({"role": "leader", "task_type": "generated",
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": user},
                                 {"role": "assistant", "content": call}]})
    for _ in range(300):
        txt = random.choice(texts)
        lang = "英文" if random.random() < 0.6 else "中文"
        user = f"把这段翻译成{lang}：{txt}"
        task = f"将以下文本翻译成{lang}：{txt}"
        call = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                f'"worker": "translate_worker", "task": "{task}"' + '}}\n</tool_call>')
        out.append({"role": "leader", "task_type": "generated",
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": user},
                                 {"role": "assistant", "content": call}]})
    for _ in range(200):
        txt = random.choice(summaries)
        user = f"帮我总结一下这段：{txt}"
        task = f"对以下文本进行摘要，不超过100字。\\n{txt}"
        call = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                f'"worker": "summary_worker", "task": "{task}"' + '}}\n</tool_call>')
        out.append({"role": "leader", "task_type": "generated",
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": user},
                                 {"role": "assistant", "content": call}]})
    # 多意图：一次派两个工人
    for i in range(200):
        tm1 = random.choice(times)
        tm2 = random.choice(times)
        if i % 2 == 0:
            ev = random.choice(events)
            rc = random.choice(remind)
            user = f"{tm1}安排{ev}，{tm2}提醒我{rc}。"
            call1 = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                     f'"worker": "calendar_worker", "task": "添加日历事件：{ev}，{tm1}。今天是2026年11月08日。"'
                     '}}\n</tool_call>')
            call2 = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                     f'"worker": "reminder_worker", "task": "设置提醒：{rc}，{tm2}。今天是2026年11月08日。"'
                     '}}\n</tool_call>')
        else:
            ev = random.choice(events)
            txt = random.choice(texts)
            user = f"{tm1}安排{ev}，另外把这段翻译成英文：{txt}"
            call1 = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                     f'"worker": "calendar_worker", "task": "添加日历事件：{ev}，{tm1}。今天是2026年11月08日。"'
                     '}}\n</tool_call>')
            call2 = ('<tool_call>\n{"name": "dispatch_to_worker", "arguments": {'
                     f'"worker": "translate_worker", "task": "将以下文本翻译成英文：{txt}"'
                     '}}\n</tool_call>')
        out.append({"role": "leader", "task_type": "generated_multi",
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": user},
                                 {"role": "assistant", "content": call1 + "\n" + call2}]})
    return out


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    # 单轮派单：过滤模糊指令
    pool = [r for r in rows if dispatch_like(r["messages"][1]["content"], r.get("task_type"))]
    random.shuffle(pool)
    single = [first_dispatch(r) for r in pool]
    single = [r for r in single if r]
    single = single[:2000]
    generated = gen_synthetic_dispatch()

    # 多轮派单：保留工具结果与汇总，抽 300
    multi_pool = [r for r in rows
                  if r.get("task_type") in ("calendar", "reminder", "translate", "summary", "mixed")
                  and len(r["messages"]) >= 4 and dispatch_like(r["messages"][1]["content"], r.get("task_type"))]
    random.shuffle(multi_pool)
    multi = multi_pool[:300]

    # clarify 600：按类分层
    clar = []
    for name in ("train.jsonl", "val.jsonl"):
        clar += [r for r in (json.loads(l) for l in open(os.path.join(CLARIFY_DIR, name), encoding="utf-8"))
                 if r.get("task_type") == "clarify"]
    by_cat = {}
    for r in clar:
        by_cat.setdefault(r["clarify_category"], []).append(r)
    quota = {"no_time": 180, "no_target": 120, "ambiguous": 150, "vague": 90,
             "contradiction": 36, "out_of_scope": 24}
    clarify = []
    for cat, q in quota.items():
        items = by_cat.get(cat, [])[:]
        random.shuffle(items)
        clarify += items[:q]

    # chat 400
    chat_pool = [r for r in rows if r.get("task_type") == "chat"]
    random.shuffle(chat_pool)
    chat = chat_pool[:400]

    allrows = single + generated + multi + clarify + chat
    random.shuffle(allrows)
    n = max(1, len(allrows) // 10)
    val, train = allrows[:n], allrows[n:]
    for name, data in (("train", train), ("val", val)):
        with open(os.path.join(OUTDIR, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {
        "single_dispatch": len(single), "generated_dispatch": len(generated), "multi_dispatch": len(multi),
        "clarify": len(clarify), "clarify_by_cat": dict(Counter(r["clarify_category"] for r in clarify)),
        "chat": len(chat), "total": len(allrows), "train": len(train), "val": len(val),
    }
    with open(os.path.join(OUTDIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
