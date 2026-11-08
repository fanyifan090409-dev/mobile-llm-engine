#!/usr/bin/env python3
"""SFT21 领队模糊指令反问数据生成。

产出：
  train/synthesize/clarify_sft21/{train.jsonl,val.jsonl,stats.json}
契约：与 cloud_sft20/leader_sft20.jsonl 一致，task_type="clarify" 的样本只有
system + user → assistant，assistant 不含 <tool_call>。

配比：
  clarify 1,000（无时间 300 / 缺主体 200 / 语义两可 250 / 指代不清 150 / 矛盾 60 / 超范围 40）
  replay  1,500（SFT20 领队派单轨迹）
  chat     300（SFT20 直答轨迹）
"""
import itertools
import json
import os
import random
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "train/synthesize/cloud_sft20/leader_sft20.jsonl")
OUTDIR = os.path.join(ROOT, "train/synthesize/clarify_sft21")
random.seed(20261108)

SYSTEM = None
rows = []
with open(SRC, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        rows.append(r)
        if SYSTEM is None:
            SYSTEM = next(m["content"] for m in r["messages"] if m["role"] == "system")
assert SYSTEM

# ---------- 无时间 ----------
NO_TIME_ACTIONS = [
    "吃药", "交作业", "给妈妈打电话", "取快递", "开会", "练听力", "背单词",
    "喝水", "牙医复诊", "体检", "家长会", "吉他课", "理发", "上教练课",
    "交房租", "打卡", "浇花", "上钢琴课", "交网费", "面试",
]
NO_TIME_PHRASES = [
    "提醒我{act}", "记得{act}", "{act}，帮我记一下", "{act}这件事帮我盯着点",
    "帮我记个事：{act}", "我要{act}，你帮我记着", "有空帮我记一下：{act}",
    "最近要{act}，别忘了", "{act}，具体时间还没定，先记下来", "帮我记一下{act}",
]
NO_TIME_SUFFIX = ["", "。", "，谢谢", "，麻烦你了"]
NO_TIME_REPLIES = [
    "可以，你想定在哪天几点？给我具体日期和时刻，我再帮你记。",
    "好，{act}想放在什么时候？说个日期和几点就行。",
    "没问题，{act}具体是哪天几点？",
    "你想哪天做这件事？再给我一个具体时刻，我好安排。",
    "时间还空着，你定个日期和几点，我来记。",
    "行，那我需要知道日期和具体时间，{act}放在什么时候？",
    "先告诉我{act}定在哪天、几点，我再往下办。",
    "你想把{act}安排在几点？给我一个具体时间就好。",
]

# ---------- 缺主体 ----------
NO_TARGET_TIMES = [
    "明天下午三点", "后天上午十点", "这周五下午", "今晚八点", "下周一上午",
    "周六下午两点", "明天中午", "下周三下午", "周五晚上", "明天上午九点",
    "后天下午", "下周二傍晚",
]
NO_TARGET_PHRASES = [
    "{t}帮我安排一下", "{t}帮我约个事", "{t}帮我留个时间", "{t}帮我记个事情",
    "{t}我要办点事，帮我排一下", "{t}帮我约一下", "{t}给我空出来，有事",
    "{t}帮我订个地方", "{t}安排个活动", "{t}帮我约个人", "{t}帮我弄个提醒",
    "{t}帮我加个日程",
]
NO_TARGET_SUFFIX = ["", "。", "，谢谢"]
NO_TARGET_REPLIES = [
    "可以，具体是什么事？告诉我事件名称，我才好写进日程。",
    "你想安排的是什么事？给我一个名称，比如开会、复诊或者上课。",
    "好，先告诉我这件事叫什么，还有大概要多久。",
    "要安排的具体内容是什么？说清楚我就能记。",
    "可以，事件名称是什么？地点和备注没有的话可以空着。",
    "你想约的是谁、做什么？给我一个具体的事情名称。",
    "这个时间我可以留出来，但得先知道是什么事。",
    "具体办什么事？给我一个标题，再说到几点结束。",
]

# ---------- 语义两可 ----------
AMBIGUOUS_ACTS = [
    "看房", "夜跑", "背单词", "复习微积分", "健身", "练听力", "写作业",
    "做实验报告", "整理错题", "准备演讲", "读文献", "练口语", "刷题",
    "学吉他", "做真题", "复盘这周的事", "预习物理", "改作文", "记笔记", "做计划",
    "晨跑", "练车", "画画", "游泳", "读原版书", "准备竞赛", "写文书",
    "查资料", "做模型", "看网课", "练琴", "准备面试", "整理房间", "做志愿",
    "背古诗", "练字", "做听力", "复习化学", "准备辩论", "写读书笔记",
]
AMBIGUOUS_SUFFIX = ["", "，帮我安排下", "，你看怎么弄", "，要不定个时间", "，安排一下",
                    "，帮我记下", "，帮我排一下"]
AMBIGUOUS_REPLIES = [
    "你是想让我帮你安排{act}的时间吗？如果是，告诉我哪天几点、大概多久。",
    "想让我把{act}加进日程吗？给我一个日期和开始时间，我来记。",
    "{act}——是要排个日程，还是只是随口说说？要排的话告诉我时间。",
    "要我帮你留出{act}的时间吗？具体哪天、几点到几点？",
    "你是想安排{act}，还是想让我提醒你？给我个时间我就能办。",
    "明白，不过{act}还需要一个具体时间。你打算哪天几点做？",
    "如果是要安排{act}，告诉我日期和时长；不是的话我就先不记。",
    "先确认一下：你是要把{act}放进日历吗？是的话说个时间。",
]

# ---------- 指代不清 ----------
VAGUE_USERS = [
    "把那个会改到下午", "删掉刚才那个提醒", "把时间往后挪一小时",
    "改到明天吧", "那个日程取消掉", "把提醒提前半小时",
    "换成下午三点", "把地点改一下", "调到周末", "帮我推迟一天",
    "把刚才那个安排到晚上", "提醒时间改成早上", "那个约改到下周",
    "把会议时间缩短一点", "把提醒删了", "时间改成两点",
    "把日程往后延", "换个会议室", "把提醒调早一点", "改到周五",
    "把那个活动改个名字", "把会挪到上午", "调整一下那个安排",
    "把刚才那个日程复制一份", "提醒改成每天", "把地点换成学校",
    "时间再晚一点", "把日程提前", "那个提醒不用了", "把时间定下来",
    "把会改到线上", "把提醒内容改一下",
]
VAGUE_SUFFIX = ["", "，谢谢", "，帮我弄下", "，可以吗"]
VAGUE_REPLIES = [
    "你说的是哪一个安排？我这边没有刚才的上下文，给我事件名称和要改的时间。",
    "要改哪个日程？告诉我事件名称，以及新的日期和几点。",
    "先告诉我具体是哪件事，再说改成什么时间，我怕改错。",
    "我还不确定你指的是哪个安排，说个事件名称或原来的时间。",
    "可以改，但要先确认是哪一条。给我事件名称和新时间。",
    "哪一件事要挪？给我名称，我才能找到它。",
    "你指的是哪个提醒或日程？说一下名字和原来定的时间。",
    "改时间没问题，先告诉我是哪件事、改到哪天几点。",
]

# ---------- 矛盾 ----------
CONTRADICTION_USERS = [
    "把明天的会改到昨天", "帮我把下周的会挪到上周三", "提醒我明天上午九点做昨天下午的事",
    "把后天的日程改到前天", "今晚八点的提醒改到昨天晚上八点", "把下个月的安排提前到上个月",
    "把明天的提醒设到昨天早上", "把下周的活动改到上周五", "把后天的会议挪到昨天",
    "把下个月的考试提醒改到上个月", "把今晚的日程改到昨晚", "把下周的课改到上周",
    "提醒我明天去参加上周的活动", "把明天的会改到大前天", "把下周的约改到去年",
]
CONTRADICTION_SUFFIX = ["", "，可以吗", "，帮我改下", "，谢谢"]
CONTRADICTION_REPLIES = [
    "这个时间对不上：已经过去的时间没法安排。你想改到未来的哪天几点？",
    "昨天已经过去了，日程不能放在过去。给我一个之后的时间吧。",
    "上周已经过了，没法挪回去。你是想改到这周或下周的哪一天？",
    "时间方向反了，只能往未来安排。说个之后的日期和时刻。",
    "这个改法会落到过去，我没法执行。你想换到哪天几点？",
    "过去的时间排不了，告诉我一个新的未来时间。",
]

# ---------- 超范围 ----------
OUT_OF_SCOPE_USERS = [
    "帮我叫个外卖", "帮我打辆车", "帮我点杯咖啡", "帮我发微信给妈妈",
    "帮我订个酒店", "帮我买张电影票", "帮我充话费", "帮我查一下快递到哪了",
    "帮我打开空调", "帮我给手机定个闹钟", "帮我转一笔钱", "帮我拍张照片",
    "帮我连一下蓝牙", "帮我下载个应用", "帮我发封邮件", "帮我改下手机密码",
    "帮我看看天气", "帮我放首歌", "帮我关灯", "帮我删除聊天记录",
]
OUT_OF_SCOPE_SUFFIX = ["", "，谢谢", "，可以吗"]
OUT_OF_SCOPE_REPLIES = [
    "这个我现在还做不了，我只能帮你安排日历和提醒。",
    "我暂时接不了这类操作，日历和提醒可以随时找我。",
    "这项能力还没接进来，目前只能帮你记日程、设提醒。",
    "抱歉，这个不在我能做的范围里。要安排日程或提醒的话我可以。",
    "我现在只能处理日历和提醒，其他操作还做不了。",
    "这个帮不上忙，我目前只会建日程和设提醒。",
]


def stable_idx(text, mod):
    return sum(ord(c) for c in text) % mod


def build(pool, n, category, reply_builder):
    """从组合池里抽样 n 条，返回 (user, assistant, category)。"""
    items = list(dict.fromkeys(pool))  # 去重且保序
    if len(items) < n:
        raise SystemExit(f"{category} 组合池不足：{len(items)} < {n}")
    picked = random.sample(items, n)
    out = []
    for user in picked:
        out.append((user, reply_builder(user), category))
    return out


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    # 无时间：20 动作 × 10 句式 × 4 后缀 = 800 组合，抽 300
    pool = [p.format(act=a) + s for a, p, s in itertools.product(
        NO_TIME_ACTIONS, NO_TIME_PHRASES, NO_TIME_SUFFIX)]
    def no_time_reply(user):
        act = next(a for a in NO_TIME_ACTIONS if a in user)
        return NO_TIME_REPLIES[stable_idx(user, len(NO_TIME_REPLIES))].format(act=act)
    clarify = build(pool, 300, "no_time", no_time_reply)

    # 缺主体：12 时间 × 12 句式 × 3 后缀 = 432，抽 200
    pool = [p.format(t=t) + s for t, p, s in itertools.product(
        NO_TARGET_TIMES, NO_TARGET_PHRASES, NO_TARGET_SUFFIX)]
    clarify += build(pool, 200, "no_target",
                     lambda u: NO_TARGET_REPLIES[stable_idx(u, len(NO_TARGET_REPLIES))])

    # 语义两可：40 动作 × 7 后缀 = 280，抽 250
    pool = [a + s for a, s in itertools.product(AMBIGUOUS_ACTS, AMBIGUOUS_SUFFIX)]
    def amb_reply(user):
        act = next(a for a in AMBIGUOUS_ACTS if user.startswith(a))
        return AMBIGUOUS_REPLIES[stable_idx(user, len(AMBIGUOUS_REPLIES))].format(act=act)
    clarify += build(pool, 250, "ambiguous", amb_reply)

    # 指代不清：32 × 4 = 128，抽 150 不够 → 补前缀组合
    vague_pool = [u + s for u, s in itertools.product(VAGUE_USERS, VAGUE_SUFFIX)]
    vague_pool += ["那个，" + u + s for u, s in itertools.product(VAGUE_USERS[:16], VAGUE_SUFFIX)]
    clarify += build(vague_pool, 150, "vague",
                     lambda u: VAGUE_REPLIES[stable_idx(u, len(VAGUE_REPLIES))])

    # 矛盾 60 / 超范围 40
    contra_pool = [u + s for u, s in itertools.product(CONTRADICTION_USERS, CONTRADICTION_SUFFIX)]
    clarify += build(contra_pool, 60, "contradiction",
                     lambda u: CONTRADICTION_REPLIES[stable_idx(u, len(CONTRADICTION_REPLIES))])
    oos_pool = [u + s for u, s in itertools.product(OUT_OF_SCOPE_USERS, OUT_OF_SCOPE_SUFFIX)]
    clarify += build(oos_pool, 40, "out_of_scope",
                     lambda u: OUT_OF_SCOPE_REPLIES[stable_idx(u, len(OUT_OF_SCOPE_REPLIES))])

    clarify_samples = [{
        "role": "leader",
        "task_type": "clarify",
        "clarify_category": cat,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": reply},
        ],
    } for user, reply, cat in clarify]

    replay_pool = [r for r in rows if r.get("task_type") in
                   ("calendar", "reminder", "translate", "summary", "mixed", "error")]
    chat_pool = [r for r in rows if r.get("task_type") == "chat"]
    random.shuffle(replay_pool)
    random.shuffle(chat_pool)
    replay = replay_pool[:1500]
    chat = chat_pool[:300]

    def split(items):
        random.shuffle(items)
        n = max(1, len(items) // 10)
        return items[n:], items[:n]

    c_train, c_val = split(clarify_samples)
    r_train, r_val = split(replay)
    h_train, h_val = split(chat)

    for name, data in [("train", c_train + r_train + h_train),
                       ("val", c_val + r_val + h_val)]:
        random.shuffle(data)
        with open(os.path.join(OUTDIR, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = {
        "system_prompt_chars": len(SYSTEM),
        "clarify": len(clarify_samples),
        "replay": len(replay),
        "chat": len(chat),
        "total": len(clarify_samples) + len(replay) + len(chat),
        "train": len(c_train) + len(r_train) + len(h_train),
        "val": len(c_val) + len(r_val) + len(h_val),
        "clarify_categories": dict(Counter(r["clarify_category"] for r in clarify_samples)),
        "replay_types": dict(Counter(r.get("task_type") for r in replay)),
        "unique_train_users": len({r["messages"][1]["content"] for r in c_train + r_train + h_train}),
    }
    with open(os.path.join(OUTDIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    bad = [r for r in clarify_samples
           if "<tool_call>" in r["messages"][2]["content"] or not r["messages"][2]["content"].strip()]
    if bad:
        raise SystemExit(f"QC_FAIL clarify 含工具调用或空回复：{len(bad)}")
    print("QC_OK")


if __name__ == "__main__":
    main()
