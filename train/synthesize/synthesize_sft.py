#!/usr/bin/env python3
"""合成手机场景 SFT 数据（六类任务画像），双 teacher 并行生成 → JSONL。

用法：
  python3 synthesize_sft.py --smoke                      # 冒烟：每类 3 条，打印样例
  python3 synthesize_sft.py --target-tokens 10000000     # 全量：目标总 tokens（含输入+输出）
  python3 synthesize_sft.py --outdir data/sft            # 输出目录（默认 data/sft）

六类占比（用户拍板手机需求画像）：翻译25 / 实时记录整理25 / 日程提醒20 / 消息文案15 / 摘要10 / 其他5。
断点续跑：启动时载入已有样本 hash，自动去重跳过。
"""
import argparse
import hashlib
import json
import os
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ENDPOINTS = [
    ("http://127.0.0.1:8002/v1/chat/completions", "qwen3.8-27b"),
    ("http://127.0.0.1:8003/v1/chat/completions", "qwen3-coder"),
]
SHARE = {"translate": 0.25, "record_tidy": 0.25, "schedule": 0.20,
         "message": 0.15, "summarize": 0.10, "misc": 0.05}
TEMPERATURE = 0.9
MAX_WORKERS = 16
DEBUG = os.environ.get("SYNTH_DEBUG") == "1"
_debug_printed = 0


def debug_print(msg):
    global _debug_printed
    if DEBUG and _debug_printed < 30:
        _debug_printed += 1
        print(f"[DEBUG] {msg}", flush=True)

# ---------- 种子语料（合成用的素材池） ----------

ZH_SENTS = [
    "帮我查一下明天北京的天气", "这件衣服能退吗，吊牌还在", "帮我记一下，周五下午三点开家长会",
    "这个药一天吃几次", "地铁到站提醒我一下", "把这段话发给我妈", "附近有什么好吃的火锅",
    "手机欠费了怎么充话费", "帮我把闹钟定到六点半", "这段话帮我翻成英文发给客户",
    "今天限号吗", "快递到哪了", "帮我写个请假条", "这个WiFi密码是多少",
    "帮我算一下268打八折是多少", "明天去医院几点挂号", "这个英文单词什么意思",
    "打车去机场要多少钱", "帮我把明天的行程排一下", "这个菜怎么做",
    "帮我发个定位给家里", "把这条消息转发到工作群", "这个月花了多少钱", "帮我查查火车票还有没有",
]
EN_SENTS = [
    "Could you please send me the meeting minutes?", "Where is the nearest subway station?",
    "I'd like to return this shirt, the tag is still on.", "Can you remind me to take my medicine at 8pm?",
    "How much is the train ticket to the airport?", "Please book a table for two tonight.",
    "My phone is running out of battery.", "What does this word mean?",
    "Can you translate this menu for me?", "I need to reschedule my appointment.",
    "Please turn on the air conditioner.", "Where can I buy a phone charger?",
    "Call my mom for me.", "Set an alarm for 6:30 tomorrow morning.",
    "How do I get to the city center?", "Please send this message to my colleague.",
    "I want to pay my credit card bill.", "Is the gym open on weekends?",
    "Can you write a leave request for me?", "How long does it take to get to the airport?",
    "Please order a taxi for me.", "What time does the pharmacy close?",
    "Can you summarize this article for me?", "Please remind me to drink water.",
]
RECORD_SCENARIOS = [
    ("团队例会", "张总", "项目进度"), ("家长会", "班主任", "孩子期中考试"),
    ("医生复诊", "王医生", "血压和用药"), ("维修师傅", "李师傅", "热水器"),
    ("朋友约饭", "小陈", "周末聚餐"), ("物业通知", "物业", "停水通知"),
    ("网课", "老师", "数学作业"), ("健身房", "教练", "训练计划"),
    ("银行电话", "客服", "信用卡账单"), ("快递电话", "快递员", "取件"),
    ("单位培训", "讲师", "安全规范"), ("旅游行程", "导游", "集合时间"),
]
ACTIVITIES = ["健身私教课", "取快递", "家长会", "复诊", "还书", "交报告", "续费会员",
              "面试", "接机", "买药", "牙医预约", "小组讨论", "送孩子上课", "缴纳水电费"]
TIME_PHRASES = ["明天下午三点", "周五晚上七点", "下周一早上八点半", "这周六中午", "后天上午十点",
                "今晚九点", "周日傍晚六点", "下周三下午两点"]
LOCATIONS = ["公司", "家里", "学校", "医院", "健身房", "咖啡店", "图书馆", "地铁站A口", "商场三楼"]
MSG_SCENARIOS = [
    ("请假", "跟老板请明天上午的假，理由：孩子学校有事"),
    ("拒绝", "婉拒朋友周末爬山邀请，因为要加班"),
    ("催办", "催同事尽快确认合同"),
    ("感谢", "感谢邻居帮忙收快递"),
    ("道歉", "为迟到半小时向朋友道歉"),
    ("砍价", "跟二手卖家砍价，从800砍到650"),
    ("邀请", "邀请朋友周五来家里吃饭"),
    ("通知", "通知室友明天停水"),
]
TONES = ["客气", "正式", "口语一点", "简短", "温和"]
TOPICS = ["手机电池保养", "如何挑选跑鞋", "北京胡同游攻略", "咖啡对睡眠的影响", "人工智能在手机上的应用",
          "居家健身入门", "秋季养生", "高效记笔记的方法", "电动车充电注意事项", "面试常见问题",
          "留学申请时间线", "睡眠质量与床垫", "家用路由器选择", "宠物猫日常护理", "短视频拍摄技巧",
          "信用卡使用避坑", "空气净化器选购", "周末短途旅行", "学生党理财", "防晒霜的正确用法"]
MISC_TOPICS = ["单位换算", "时间计算", "汇率换算", "手机设置", "生活常识", "健康常识",
               "交通出行", "饮食营养", "天气相关", "购物建议", "学习技巧", "网络安全"]

# ---------- 基础调用 ----------

def chat(endpoint, model, messages, max_tokens=512, temperature=TEMPERATURE):
    """单次补全，带重试，返回 OpenAI 兼容响应。

    固定 enable_thinking=false：两个 teacher 都是思考型模型，
    关掉思考既防止思考 token 吃满预算导致空回复（30B 实测），
    也让输出不掺思维链文本（27B abliterated 实测会把 CoT 当正文吐出来）。
    """
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens,
               "temperature": temperature, "top_p": 0.95, "stream": False,
               "chat_template_kwargs": {"enable_thinking": False}}
    last = None
    for i in range(3):
        try:
            r = requests.post(endpoint, json=payload, timeout=600)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # 网络抖动/服务忙重试
            last = e
            time.sleep(2 * (i + 1))
    raise last

def content_of(resp):
    return (resp["choices"][0]["message"].get("content") or "").strip()

# ---------- 六类任务构建器 ----------

def build_translate(rng):
    if rng.random() < 0.5:
        zh = rng.choice(ZH_SENTS)
        instr = rng.choice(["把这句话翻译成自然的口语英文：", "帮我把这句中文翻成英文，口语一点：", "翻译成英文："])
        return {"kind": "simple", "messages": [{"role": "user", "content": instr + zh}], "max_tokens": 256}
    en = rng.choice(EN_SENTS)
    instr = rng.choice(["把这句话翻译成自然的中文：", "帮我把这句英文翻成中文，口语一点：", "翻译成中文："])
    return {"kind": "simple", "messages": [{"role": "user", "content": instr + en}], "max_tokens": 256}

def build_record_tidy(rng):
    topic, person, detail = rng.choice(RECORD_SCENARIOS)
    parts = [
        f"{person}说了{topic}的事，主要是{detail}。",
        f"提到了两个时间点：{rng.choice(TIME_PHRASES)}和{rng.choice(TIME_PHRASES)}。",
        f"最后强调{rng.choice(['要提前准备材料', '别忘了带证件', '有问题随时联系', '下次碰头再确认'])}。",
    ]
    transcript = ""
    for p in parts:
        transcript += p
        if rng.random() < 0.5:  # 模拟语音转写口语噪声（嗯/那个/重复）
            transcript += rng.choice(["嗯", "那个", "就是说", "然后"])
    user = f"下面是一段手机语音转写出来的文字，帮我整理成清晰的要点和行动项：\n{transcript}"
    return {"kind": "simple", "messages": [{"role": "user", "content": user}], "max_tokens": 512}

# 合成期专用 system 提示（不写入数据集）：控制 teacher 输出格式，
# 数据集中的 user 消息保持干净，轨迹为标准 tool-call 形式。
SYNTH_SYS_SCHED1 = ("你是手机助手。当用户要求添加日历事件时，只输出一个工具调用块，"
                    "不要输出任何其他内容，格式：\n"
                    "<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": "
                    "{\"title\": \"事件名称\", \"start_time\": \"YYYY-MM-DD HH:mm\", "
                    "\"end_time\": \"YYYY-MM-DD HH:mm\", \"location\": \"地点\", \"note\": \"备注\"}}\n</tool_call>")
SYNTH_SYS_SCHED2 = ("你是手机助手。日历工具已成功添加事件。请用一句自然的中文向用户确认"
                    "（提及事件名称、时间、地点），不要输出工具调用或任何其他格式。")

def build_schedule(rng):
    activity = rng.choice(ACTIVITIES)
    t = rng.choice(TIME_PHRASES)
    loc = rng.choice(LOCATIONS)
    user = (f"帮我在手机日历里加一个事件：{activity}，时间{t}，地点{loc}。\n"
            f"日期用2026年11月里的日子，时长约一小时。")
    spec = {"kind": "schedule", "messages": [{"role": "user", "content": user}], "max_tokens": 1024}
    spec["synthesis_system"] = SYNTH_SYS_SCHED1
    return spec

def build_message(rng):
    mtype, context = rng.choice(MSG_SCENARIOS)
    tone = rng.choice(TONES)
    user = f"帮我写一条{mtype}消息：{context}。语气{tone}。"
    return {"kind": "simple", "messages": [{"role": "user", "content": user}], "max_tokens": 384}

def build_summarize(rng):
    topic = rng.choice(TOPICS)
    user = f"请写一篇关于「{topic}」的短文（300字左右），写完后另起一行用【摘要】开头，写一段50字以内的摘要。"
    return {"kind": "summarize", "messages": [{"role": "user", "content": user}], "max_tokens": 768}

def build_misc(rng):
    topic = rng.choice(MISC_TOPICS)
    user = f"生成5个手机用户常见问题及简短答案，主题：{topic}。每条格式：Q：…\nA：…"
    return {"kind": "misc", "messages": [{"role": "user", "content": user}], "max_tokens": 512}

BUILDERS = {"translate": build_translate, "record_tidy": build_record_tidy,
            "schedule": build_schedule, "message": build_message,
            "summarize": build_summarize, "misc": build_misc}

def pick_category(rng):
    r = rng.random()
    acc = 0.0
    for c, s in SHARE.items():
        acc += s
        if r <= acc:
            return c
    return "misc"

# ---------- 任务执行（含各类后处理/校验） ----------

def run_schedule(endpoint, model, spec):
    """日程类：teacher 在合成期 system 提示下输出 Qwen3 风格 <tool_call> XML，
    脚本校验参数后回填工具结果，二调用出确认话术（同样用合成期 system 引导）。
    写入数据集的轨迹不含 system 消息：user → tool_call → tool 结果 → 确认。"""
    msgs1 = [{"role": "system", "content": spec["synthesis_system"]}] + spec["messages"]
    resp = chat(endpoint, model, msgs1, max_tokens=spec["max_tokens"])
    tks = resp.get("usage", {}).get("total_tokens", 0)
    raw = content_of(resp)
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", raw, re.S)
    if not m:
        debug_print(f"schedule 首调用无XML | finish={resp['choices'][0].get('finish_reason')} | raw={raw[:150]!r}")
        return [], tks
    try:
        call_obj = json.loads(m.group(1))
        if call_obj.get("name") != "add_calendar_event":
            return [], tks
        args_obj = call_obj.get("arguments") or {}
        for k in ("title", "start_time", "end_time"):  # 参数不完整即丢弃该样本
            if k not in args_obj:
                return [], tks
        for k in ("start_time", "end_time"):  # 时间必须可解析格式
            if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", str(args_obj[k])):
                return [], tks
    except Exception:
        return [], tks
    tool_msg = {"role": "tool", "tool_call_id": "call_" + uuid.uuid4().hex[:8],
                "content": json.dumps({"status": "ok", "event_id": "evt_" + uuid.uuid4().hex[:8]},
                                      ensure_ascii=False)}
    asst_call = {"role": "assistant",
                 "content": "<tool_call>\n" + json.dumps(call_obj, ensure_ascii=False) + "\n</tool_call>"}
    msgs2 = ([{"role": "system", "content": SYNTH_SYS_SCHED2}] + spec["messages"]
             + [asst_call, tool_msg])
    resp2 = chat(endpoint, model, msgs2, max_tokens=256)
    tks += resp2.get("usage", {}).get("total_tokens", 0)
    final = content_of(resp2) or "好的，已帮你添加到日历。"
    return [{"messages": spec["messages"] + [asst_call, tool_msg,
                                             {"role": "assistant", "content": final}]}], tks

def run_summarize(endpoint, model, spec):
    """摘要类：一次调用产出「原文+摘要」，拆成 输入=原文、输出=摘要 的样本。
    偶发漏【摘要】标记，重试一次。"""
    tks = 0
    for attempt in range(2):
        resp = chat(endpoint, model, spec["messages"], max_tokens=spec["max_tokens"])
        tks += resp.get("usage", {}).get("total_tokens", 0)
        out = content_of(resp)
        if "【摘要】" in out:
            break
        debug_print(f"summarize 无摘要标记(第{attempt + 1}次) | finish={resp['choices'][0].get('finish_reason')} | out={out[:100]!r}")
    else:
        return [], tks
    article, summary = out.split("【摘要】", 1)
    article, summary = article.strip(), summary.strip()
    if len(article) < 50 or not summary:
        debug_print(f"summarize 原文过短或摘要为空 | article_len={len(article)}")
        return [], tks
    user = f"帮我总结一下这篇文章的要点：\n{article}"
    return [{"messages": [{"role": "user", "content": user},
                          {"role": "assistant", "content": summary}]}], tks

def run_misc(endpoint, model, spec):
    """其他类：一次调用出5对问答，拆成独立样本。"""
    resp = chat(endpoint, model, spec["messages"], max_tokens=spec["max_tokens"])
    tks = resp.get("usage", {}).get("total_tokens", 0)
    out = content_of(resp)
    samples, q = [], None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Q") and "：" in line:
            q = line.split("：", 1)[1].strip()
        elif line.startswith("A") and "：" in line and q:
            a = line.split("：", 1)[1].strip()
            if a:
                samples.append({"messages": [{"role": "user", "content": q},
                                             {"role": "assistant", "content": a}]})
            q = None
    return samples, tks

def run_task(task):
    """执行一个合成任务，返回 (样本列表, 消耗tokens)。异常即丢弃。"""
    idx, spec = task
    if spec["kind"] == "schedule":
        endpoint, model = ENDPOINTS[1]  # 仅 30B 能稳定输出工具调用 XML（27B 实测拒答）
    else:
        endpoint, model = ENDPOINTS[idx % len(ENDPOINTS)]
    try:
        if spec["kind"] == "schedule":
            samples, tks = run_schedule(endpoint, model, spec)
        elif spec["kind"] == "summarize":
            samples, tks = run_summarize(endpoint, model, spec)
        elif spec["kind"] == "misc":
            samples, tks = run_misc(endpoint, model, spec)
        else:
            resp = chat(endpoint, model, spec["messages"], max_tokens=spec["max_tokens"])
            out = content_of(resp)
            tks = resp.get("usage", {}).get("total_tokens", 0)
            if not out:
                debug_print(f"{spec['category']} 空回复 | finish={resp['choices'][0].get('finish_reason')} | model={model}")
                return [], tks
            samples = [{"messages": spec["messages"] + [{"role": "assistant", "content": out}]}]
        for s in samples:
            s["category"] = spec["category"]
        return samples, tks
    except Exception as e:
        debug_print(f"{spec['category']} 异常 | {type(e).__name__}: {e}")
        return [], 0

# ---------- 主流程 ----------

def load_seen(outdir):
    seen = set()
    if not os.path.isdir(outdir):
        return seen
    for fn in os.listdir(outdir):
        if fn.endswith(".jsonl"):
            with open(os.path.join(outdir, fn), encoding="utf-8") as f:
                for line in f:
                    try:
                        seen.add(json.loads(line)["hash"])
                    except Exception:
                        pass
    return seen

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="冒烟：每类3条并打印样例")
    ap.add_argument("--target-tokens", type=int, default=10_000_000)
    ap.add_argument("--outdir", default="data/sft")
    ap.add_argument("--seed", type=int, default=20261023)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.outdir, exist_ok=True)
    seen = load_seen(args.outdir)
    files = {c: open(os.path.join(args.outdir, f"{c}.jsonl"), "a", encoding="utf-8") for c in SHARE}
    cat_counts = {c: 0 for c in SHARE}
    total_tokens, total_samples, dup_skip = 0, 0, 0
    started = time.time()

    def make_task(i):
        if args.smoke:
            c = list(SHARE)[i % len(SHARE)]
        else:
            c = pick_category(rng)
        spec = BUILDERS[c](rng)
        spec["category"] = c
        return (i, spec)

    smoke_limit = 3 * len(SHARE)
    idx, stop, tasks_done = 0, False, 0
    last_log_hundred = -1
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for _ in range(MAX_WORKERS):
            futs[ex.submit(run_task, make_task(idx))] = idx
            idx += 1
        while futs and not stop:
            for fut in as_completed(futs):
                futs.pop(fut)
                samples, tks = fut.result()
                total_tokens += tks
                for s in samples:
                    h = hashlib.sha256(json.dumps(s["messages"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
                    if h in seen:
                        dup_skip += 1
                        continue
                    seen.add(h)
                    s["hash"] = h
                    files[s["category"]].write(json.dumps(s, ensure_ascii=False) + "\n")
                    cat_counts[s["category"]] += 1
                    total_samples += 1
                tasks_done += 1
                # 冒烟按任务数收口（按样本数会因 misc 1拆5 提前停止，
                # 慢任务 schedule/summarize 在途被放弃，冒烟看不到它们）
                if args.smoke and tasks_done >= smoke_limit:
                    stop = True
                elif not args.smoke and total_tokens >= args.target_tokens:
                    stop = True
                if stop:
                    break
                futs[ex.submit(run_task, make_task(idx))] = idx
                idx += 1
                hundred = total_samples // 100
                if hundred != last_log_hundred:
                    last_log_hundred = hundred
                    el = time.time() - started
                    print(f"[{time.strftime('%H:%M:%S')}] 样本 {total_samples} | tokens {total_tokens/1e6:.2f}M | "
                          f"速率 {total_tokens/el:.0f} tok/s | 去重跳过 {dup_skip}", flush=True)
        for f in futs:
            f.cancel()

    meta = {"samples": total_samples, "tokens": total_tokens, "dup_skipped": dup_skip,
            "elapsed_s": round(time.time() - started), "category_counts": cat_counts}
    with open(os.path.join(args.outdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    for f in files.values():
        f.close()
    print(json.dumps(meta, ensure_ascii=False))

    if args.smoke:
        # 每类打印 1 条样例供人工检查
        for c in SHARE:
            path = os.path.join(args.outdir, f"{c}.jsonl")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    print("-" * 60)
                    print(f"[类别 {c}]")
                    for m in rec["messages"]:
                        if m.get("content"):
                            print(f"  [{m['role']}] {str(m['content'])[:150]}")
                        elif m.get("tool_calls"):
                            print(f"  [{m['role']}] tool_call {str(m['tool_calls'])[:150]}")
                    break

if __name__ == "__main__":
    main()
