#!/usr/bin/env python3
"""合成 SFT19 学术能力数据（AP 微积分 / 美高 Precalculus / AP 统计 / 雅思），双 teacher 并行生成 → JSONL。

用法：
  python3 synthesize_academic.py --smoke                 # 冒烟：每类 3 条，打印样例
  python3 synthesize_academic.py --target-tokens 10000000 # 全量：目标总 tokens
  python3 synthesize_academic.py --outdir data/sft19     # 输出目录（默认 data/sft19）

四类占比（SFT19 计划 §2.2 用户拍板）：ap_calc 40 / precalc 20 / ap_stats 15 / ielts 25。
教师分配（§2.3）：ap_calc/precalc/ap_stats → 30B-A3B(:8003，coder 血统数学稳)；ielts → 27B(:8002)。
出题类样本按 --holdout-ratio 抽留 holdout（不进训练集，验收期评测用）。
格式契约（QC 依据，与 qc_sft.py 学术检查对应）：
  ap 出题/雅思生成类：assistant 内容必须含对应【】标记块且非空；
  ap 解题类（SFT19 升级）：assistant 必须含【思路】【解答】【答案】三块（分步理由+验算）。
断点续跑：启动时载入已有样本 hash，自动去重跳过。
"""
import argparse
import hashlib
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ENDPOINTS = [
    ("http://127.0.0.1:8002/v1/chat/completions", "qwen3.8-27b"),
    ("http://127.0.0.1:8003/v1/chat/completions", "qwen3-coder"),
]
IELTS_EP = 0   # 27B 长文本生成快
AP_EP = 1      # 30B-A3B 数学推理稳
SHARE = {"ap_calc": 0.40, "precalc": 0.20, "ap_stats": 0.15, "ielts": 0.25}
TEMPERATURE = 0.9
MAX_WORKERS = 4  # 学术任务输出长（1280-2048 tokens），16 并发会把单卡 vLLM 吞吐挤爆（冒烟实测 48 tok/s）
DEBUG = os.environ.get("SYNTH_DEBUG") == "1"
_debug_printed = 0


def debug_print(msg):
    global _debug_printed
    if DEBUG and _debug_printed < 30:
        _debug_printed += 1
        print(f"[DEBUG] {msg}", flush=True)

# ---------- 种子语料 ----------

# AP 微积分 AB/BC 知识点（按 College Board 单元划分，中英混写便于 teacher 出题）
AP_CALC_TOPICS = [
    ("极限与连续性", ["极限的代数计算", "无穷极限与渐近线", "介值定理", "连续性与间断点"]),
    ("导数定义与基本规则", ["导数定义与可导性", "幂/积/商法则", "链式法则", "隐函数求导", "反函数求导"]),
    ("导数应用", ["相关变化率", "中值定理", "一阶/二阶导数与图像分析", "最优化问题", "洛必达法则"]),
    ("积分与微积分基本定理", ["黎曼和与定积分", "原函数与不定积分", "微积分基本定理", "换元积分法", "反常积分"]),
    ("积分应用", ["平面区域面积", "旋转体体积", "弧长", "平均值定理", "累积函数"]),
    ("微分方程", ["分离变量法", "欧拉法", "逻辑斯蒂模型", "斜率场", "指数增长与衰减"]),
    ("参数方程/极坐标/向量", ["参数方程求导", "极坐标面积", "极坐标求导", "运动学（位移/速度/加速度）"]),
    ("级数", ["收敛判别法（比值/根值/比较）", "交错级数与误差界", "泰勒与麦克劳林级数", "拉格朗日误差界", "幂级数收敛区间"]),
]
AP_CALC_DIFF = ["基础", "中等", "较难"]
AP_CALC_FORM = ["出题", "解题"]

# 美高数学（Precalculus / Algebra 2 / Trigonometry，SFT19 新增：微积分前置知识谱系）
PRECALC_TOPICS = [
    ("代数基础（Algebra 2）", ["多项式运算与因式分解", "有理表达式化简", "指数与对数函数", "复数运算", "二次函数与抛物线", "函数变换与图像"]),
    ("方程与不等式", ["二次方程与判别式", "高次方程与有理根定理", "指数/对数方程", "绝对值不等式", "线性规划", "二元方程组"]),
    ("函数", ["定义域与值域", "反函数", "复合函数", "分段函数", "奇偶性与对称性", "图像平移与伸缩"]),
    ("三角函数", ["弧度制与单位圆", "正弦/余弦图像与变换", "三角恒等式", "解三角形（正弦/余弦定理）", "反三角函数", "三角方程"]),
    ("极坐标与参数方程初步", ["极坐标与直角坐标互化", "极坐标图形", "参数方程与消参", "圆锥曲线初步"]),
    ("数列与级数初步", ["等差数列", "等比数列", "求和符号", "二项式定理", "数学归纳法"]),
    ("解析几何", ["直线方程", "圆", "椭圆/双曲线/抛物线", "距离与中点公式"]),
    ("向量与矩阵初步", ["向量运算", "点积", "矩阵基本运算", "行列式与面积"]),
]
PRECALC_DIFF = ["基础", "中等", "较难"]

# AP 统计知识点（College Board 单元）
AP_STATS_TOPICS = [
    ("单变量数据分析", ["分布形状/中心/离散度", "箱线图与异常值", "直方图与茎叶图", "z 分数与正态分布"]),
    ("双变量数据分析", ["散点图与相关", "最小二乘回归线", "残差与决定系数", "非线性转换"]),
    ("抽样与实验设计", ["简单随机抽样", "分层/整群抽样", "完全随机实验设计", "区组设计与配对设计", "偏差与混杂"]),
    ("概率基础", ["概率规则", "条件概率与独立性", "贝叶斯思想", "模拟"]),
    ("随机变量", ["离散随机变量期望与方差", "二项分布", "几何分布", "二项/几何分布条件"]),
    ("抽样分布", ["样本均值抽样分布", "样本比例抽样分布", "中心极限定理", "无偏性与变异性"]),
    ("置信区间", ["均值的 t 区间", "比例的 z 区间", "区间解释与条件"]),
    ("假设检验", ["均值的 t 检验", "比例的 z 检验", "p 值与显著性", "第一/二类错误与功效"]),
    ("卡方检验", ["拟合优度", "独立性检验", "同质性检验"]),
    ("回归推断", ["斜率推断", "斜率置信区间", "斜率检验"]),
]
AP_STATS_DIFF = ["基础", "中等", "较难"]

# 雅思素材
IELTS_WRITING_T1 = [
    ("线图", "1990-2020 年某市三种出行方式（公交/私家车/地铁）使用比例变化"),
    ("柱状图", "五个国家居民每周平均工作时长对比"),
    ("饼图", "某大学学生每月生活开支构成"),
    ("表格", "四个城市人口、平均气温与年降雨量数据"),
    ("地图", "某小镇 2000 年与 2020 年布局变化对比"),
    ("流程图", "废纸回收再利用的完整流程"),
]
IELTS_WRITING_T2_TOPICS = [
    "越来越多人在家办公，这是利大于弊还是弊大于利？",
    "政府是否应该投资公共交通而不是修更多公路？",
    "大学教育是否应该免费？",
    "青少年使用社交媒体的影响是积极还是消极？",
    "是否应该禁止一次性塑料制品？",
    "城市化对传统社区的影响是利是弊？",
    "学校应该教更多实用技能而不是理论知识吗？",
    "人工智能发展对就业市场的影响是机遇还是威胁？",
    "家长是否应该限制孩子使用电子设备的时间？",
    "旅游业对发展中国家经济和文化的影响？",
]
IELTS_READING_THEMES = [
    "教育", "环境保护", "科技发展", "健康与医疗", "历史考古", "动物行为",
    "城市交通", "能源", "心理学", "经济学常识",
]
IELTS_READING_TYPES = [
    "判断题（TRUE/FALSE/NOT GIVEN）", "选择题（四选一）", "标题匹配（matching headings）",
    "信息匹配（matching information）", "摘要填空题（summary completion）",
    "句子填空题（sentence completion）",
]
IELTS_LISTENING_SECS = [
    ("Section 1", "租房咨询电话", "note/form completion"),
    ("Section 1", "旅行预订对话", "table completion"),
    ("Section 2", "博物馆参观导览独白", "map/matching"),
    ("Section 2", "社区活动介绍独白", "multiple choice"),
    ("Section 3", "师生讨论研究项目", "multiple choice"),
    ("Section 3", "小组作业讨论", "matching"),
    ("Section 4", "学术讲座（环境科学）", "note completion"),
    ("Section 4", "学术讲座（历史主题）", "summary completion"),
]

# ---------- 基础调用 ----------

def chat(endpoint, model, messages, max_tokens=512, temperature=TEMPERATURE):
    """单次补全，带重试，返回 OpenAI 兼容响应。固定 enable_thinking=false（同 synthesize_sft.py）。"""
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

# ---------- 任务构建器 ----------

def _subject_of(category):
    return {"ap_calc": "AP 微积分", "precalc": "美高数学（Precalculus/Algebra 2）",
            "ap_stats": "AP 统计"}[category]


def _topics_diff_of(rng, category):
    if category == "ap_calc":
        return rng.choice(AP_CALC_TOPICS), AP_CALC_DIFF
    if category == "precalc":
        return rng.choice(PRECALC_TOPICS), PRECALC_DIFF
    return rng.choice(AP_STATS_TOPICS), AP_STATS_DIFF


def build_ap_problem_gen(rng, category):
    """出题方向：user 指定知识点+难度 → assistant 产出 题目+答案+解答步骤。"""
    (unit, subtopics), diffs = _topics_diff_of(rng, category)
    subtopic = rng.choice(subtopics)
    diff = rng.choice(diffs)
    subject = _subject_of(category)
    user = (f"请围绕知识点「{unit}——{subtopic}」出一道{diff}难度的{subject}练习题。"
            "要求：题目完整自洽（数据/条件齐全），答案正确，并给出详细解答步骤。"
            "严格按以下格式输出：\n【题目】…\n【答案】…\n【解答】…")
    return {"kind": "gen", "form": "problem_gen",
            "messages": [{"role": "user", "content": user}], "max_tokens": 1536}


def build_ap_solve(rng, category):
    """解题方向：先让 teacher 出题（仅题目），再把题目作为 user 消息让 teacher 解答。
    两条样本：出题轨迹 + 解题轨迹（同一题各写一份，避免题目/解答对不上）。
    SFT19 解答升级：要求【思路】（2-4 句规划）→【解答】（分步编号带理由）→【答案】（单独一行+验算）。"""
    (unit, subtopics), diffs = _topics_diff_of(rng, category)
    subtopic = rng.choice(subtopics)
    diff = rng.choice(diffs)
    subject = _subject_of(category)
    gen_user = (f"请围绕知识点「{unit}——{subtopic}」出一道{diff}难度的{subject}练习题，"
                "题目完整自洽（数据/条件齐全）。只输出题目，不要答案和解答。格式：\n【题目】…")
    spec = {"kind": "solve", "form": "solve",
            "messages": [{"role": "user", "content": gen_user}], "max_tokens": 1024}
    spec["solve_subject"] = subject
    return spec


# 雅思写作风格契约（2026-11-02 用户拍板）：模拟亚洲（中国）考生真人答卷——高质量
# 但低 AI 检测率。禁用 AI 特征词/模板句，允许少量真人不完美，杜绝「范文腔」。
IELTS_STYLE = ("写作风格要求（重要）：模拟中国大陆雅思考生真人答卷，目标 band 7.5-8，"
               "不是范文腔。1) 结构自然：开头直入主题不背模板套句，主体两段论证，结尾自然收束；"
               "2) 词汇：学术常用词即可，不堆砌生僻词；3) 句式长短结合，允许少量真人不完美"
               "（如个别搭配略生硬、偶见中式思维痕迹），但整体连贯、论证扎实；"
               "4) 严禁 AI 特征表达：delve、pivotal、paramount、multifaceted、tapestry、"
               "a double-edged sword、It is widely acknowledged、In today's society、"
               "Moreover/Furthermore/Additionally 连发、Firstly/Secondly/Finally 死板框架、"
               "每段以 In conclusion 收尾等模板痕迹。")


def build_ielts_writing(rng):
    if rng.random() < 0.45:
        ctype, desc = rng.choice(IELTS_WRITING_T1)
        user = (f"雅思写作 Task 1（图表题）：{ctype}——{desc}。"
                f"请以亚洲考生真人风格写一篇 150 词左右的英文描述（不是范文腔）。{IELTS_STYLE}"
                "写完后另起一行用【点评】开头，"
                "用中文从任务回应、连贯与衔接、词汇、语法四个维度各点评两句。")
        return {"kind": "gen", "form": "ielts_writing",
                "messages": [{"role": "user", "content": user}], "max_tokens": 1024}
    topic = rng.choice(IELTS_WRITING_T2_TOPICS)
    user = (f"雅思写作 Task 2（议论文）：{topic}。"
            f"请以亚洲考生真人风格写一篇 250 词左右的英文作文（不是范文腔）。{IELTS_STYLE}"
            "写完后另起一行用【点评】开头，"
            "用中文从任务回应、连贯与衔接、词汇、语法四个维度各点评两句。")
    return {"kind": "gen", "form": "ielts_writing",
            "messages": [{"role": "user", "content": user}], "max_tokens": 1280}


def build_ielts_reading(rng):
    theme = rng.choice(IELTS_READING_THEMES)
    qtype = rng.choice(IELTS_READING_TYPES)
    user = (f"请生成一篇雅思阅读练习题：主题「{theme}」。"
            f"要求：英文文章 600 词左右，出 6 道{qtype}（题目用中文表述），"
            "并给出答案和中文解析。严格按以下格式输出：\n"
            "【文章】…\n【题目】…\n【答案】…\n【解析】…")
    return {"kind": "gen", "form": "ielts_reading",
            "messages": [{"role": "user", "content": user}], "max_tokens": 2048}


def build_ielts_listening(rng):
    sec, scene, qtype = rng.choice(IELTS_LISTENING_SECS)
    user = (f"请生成一段雅思听力练习材料：{sec}（{scene}）。"
            f"要求：英文听力文本 300 词左右，出 5 道{qtype}题（题目用中文表述），"
            "并给出答案和中文解析。严格按以下格式输出：\n"
            "【听力文本】…\n【题目】…\n【答案】…\n【解析】…")
    return {"kind": "gen", "form": "ielts_listening",
            "messages": [{"role": "user", "content": user}], "max_tokens": 1536}


def pick_form_ap(rng):
    return "出题" if rng.random() < 0.6 else "解题"


BUILDERS = {"ap_calc": build_ap_problem_gen, "precalc": build_ap_problem_gen,
            "ap_stats": build_ap_problem_gen, "ielts": build_ielts_writing}


def pick_category(rng):
    r = rng.random()
    acc = 0.0
    for c, s in SHARE.items():
        acc += s
        if r <= acc:
            return c
    return "ielts"


def build_spec(rng, category):
    """按类别和子形式选构建器。"""
    if category in ("ap_calc", "precalc", "ap_stats"):
        if pick_form_ap(rng) == "出题":
            spec = build_ap_problem_gen(rng, category)
        else:
            spec = build_ap_solve(rng, category)
    else:  # ielts 三子类：写作/阅读/听力
        r = rng.random()
        if r < 0.40:
            spec = build_ielts_writing(rng)
        elif r < 0.70:
            spec = build_ielts_reading(rng)
        else:
            spec = build_ielts_listening(rng)
    spec["category"] = category
    return spec

# ---------- 校验与后处理 ----------

# 各类生成样本的标记块契约（QC 与 qc_sft.py 学术检查共用）
GEN_MARKERS = {
    "problem_gen": ["【题目】", "【答案】", "【解答】"],
    "ielts_writing": ["【点评】"],
    "ielts_reading": ["【文章】", "【题目】", "【答案】", "【解析】"],
    "ielts_listening": ["【听力文本】", "【题目】", "【答案】", "【解析】"],
}


def section_nonempty(out, marker):
    """标记块必须非空（标记后到下一标记或结尾之间的内容 ≥20 字）。"""
    parts = out.split(marker)
    if len(parts) < 2:
        return False
    seg = parts[1]
    for m in GEN_MARKERS.get("", []):
        pass
    # 截到下一个【】标记为止
    for other in ("【题目】", "【答案】", "【解答】", "【点评】", "【解析】", "【文章】", "【听力文本】"):
        if other == marker:
            continue
        if other in seg:
            seg = seg.split(other)[0]
    return len(seg.strip()) >= 20


def validate_gen(form, out):
    if form not in GEN_MARKERS:
        return False
    for marker in GEN_MARKERS[form]:
        if marker not in out or not section_nonempty(out, marker):
            return False
    # 公式残缺粗查：出现孤立美元符号或反斜杠结尾（LaTeX 被截断的特征）
    if out.count("$") % 2 != 0 or out.rstrip().endswith("\\"):
        return False
    return True


def run_gen(endpoint, model, spec):
    """生成类（出题/雅思三类）：一次调用产出完整材料，校验标记块后入库。
    并发下 teacher 偶发写到一半就停（stop 但块不全），校验失败重试一次。"""
    tks = 0
    for attempt in range(2):
        resp = chat(endpoint, model, spec["messages"], max_tokens=spec["max_tokens"])
        tks += resp.get("usage", {}).get("total_tokens", 0)
        out = content_of(resp)
        if not out:
            debug_print(f"{spec['category']}/{spec['form']} 空回复(第{attempt + 1}次) | finish={resp['choices'][0].get('finish_reason')}")
            continue
        if validate_gen(spec["form"], out):
            break
        debug_print(f"{spec['category']}/{spec['form']} 标记块校验失败(第{attempt + 1}次) | out={out[:120]!r}")
    else:
        return [], tks
    samples = [{"messages": spec["messages"] + [{"role": "assistant", "content": out}]}]
    for s in samples:
        s["category"] = spec["category"]
        s["form"] = spec["form"]
    return samples, tks


def run_solve(endpoint, model, spec):
    """解题类（ap）：调用1出题 → 调用2解题，产出两条样本（出题轨迹+解题轨迹）。
    题目/解答天然配对，避免 teacher 解错自出题。"""
    tks = 0
    resp = chat(endpoint, model, spec["messages"], max_tokens=spec["max_tokens"])
    tks += resp.get("usage", {}).get("total_tokens", 0)
    problem = content_of(resp)
    if "【题目】" not in problem or not section_nonempty(problem, "【题目】"):
        debug_print(f"{spec['category']}/solve 出题失败 | out={problem[:120]!r}")
        return [], tks
    # 只保留【题目】块，格式统一
    problem_text = problem.split("【题目】", 1)[1]
    for other in ("【答案】", "【解答】", "【解析】"):
        if other in problem_text:
            problem_text = problem_text.split(other)[0]
    problem_text = problem_text.strip()
    if len(problem_text) < 40:
        return [], tks
    # 样本1：出题轨迹（user 要题 → assistant 给题）
    samples = [{"messages": spec["messages"] + [{"role": "assistant", "content": "【题目】" + problem_text}]}]
    # 调用2：解题（user 给题 → assistant 给三块解答：思路/分步理由/答案+验算）
    solve_user = (f"请解答下面这道{spec['solve_subject']}题。严格按以下格式输出：\n"
                  "【思路】先用 2-4 句说明解题规划（用什么方法、为什么适用）；\n"
                  "【解答】分步编号写出详细步骤，每步说明理由（为什么这么做），不跳步；\n"
                  "【答案】单独一行给出最终结果，并验算确认。\n"
                  "题目：\n" + problem_text)
    resp2 = chat(endpoint, model, [{"role": "user", "content": solve_user}],
                 max_tokens=1536)
    tks += resp2.get("usage", {}).get("total_tokens", 0)
    solution = content_of(resp2)
    # 解题失败时出题轨迹样本仍有效，但必须补 category/form 再返回
    # （2026-11-02 实发：三块缺失路径直接 return 未打字段样本 → main KeyError 崩全链）
    def _stamp(samples):
        for s in samples:
            s["category"] = spec["category"]
            s["form"] = "solve"
        return samples, tks
    if not all(f"【{b}】" in solution for b in ("思路", "解答", "答案")):
        debug_print(f"{spec['category']}/solve 三块标记缺失 | out={solution[:120]!r}")
        return _stamp(samples)
    if len(solution) < 200:  # 思路+分步理由+验算，不能是空壳
        debug_print(f"{spec['category']}/solve 解答过短 | len={len(solution)} | out={solution[:120]!r}")
        return _stamp(samples)
    samples.append({"messages": [{"role": "user", "content": solve_user},
                                 {"role": "assistant", "content": solution}]})
    for s in samples:
        s["category"] = spec["category"]
        s["form"] = "solve"
    return samples, tks


def run_task(task):
    """执行一个合成任务，返回 (样本列表, 消耗tokens)。异常即丢弃。"""
    idx, spec = task
    endpoint, model = ENDPOINTS[AP_EP if spec["category"] in ("ap_calc", "precalc", "ap_stats") else IELTS_EP]
    try:
        if spec["kind"] == "gen":
            samples, tks = run_gen(endpoint, model, spec)
        else:
            samples, tks = run_solve(endpoint, model, spec)
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
    ap.add_argument("--outdir", default="data/sft19")
    ap.add_argument("--holdout-ratio", type=float, default=0.03,
                    help="出题类样本留作 holdout 的比例（验收期评测，不进训练集）")
    ap.add_argument("--seed", type=int, default=20261102)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.outdir, exist_ok=True)
    os.makedirs(os.path.join(args.outdir, "holdout"), exist_ok=True)
    seen = load_seen(args.outdir)
    # holdout 单独计数（文件名含 holdout 前缀，load_seen 只看主目录 *.jsonl 不冲突）
    files = {}
    for c in SHARE:
        files[c] = open(os.path.join(args.outdir, f"{c}.jsonl"), "a", encoding="utf-8")
    hold_files = {c: open(os.path.join(args.outdir, "holdout", f"{c}.jsonl"), "a", encoding="utf-8")
                  for c in SHARE}
    cat_counts = {c: 0 for c in SHARE}
    hold_counts = {c: 0 for c in SHARE}
    total_tokens, total_samples, dup_skip = 0, 0, 0
    started = time.time()

    def make_task(i):
        c = list(SHARE)[i % len(SHARE)] if args.smoke else pick_category(rng)
        spec = build_spec(rng, c)
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
                    # 防御：缺 category 的坏样本直接丢弃（2026-11-02 实发 KeyError 崩全链）
                    if s.get("category") not in files:
                        debug_print(f"样本缺 category 字段，丢弃 | keys={list(s)}")
                        continue
                    h = hashlib.sha256(json.dumps(s["messages"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
                    if h in seen:
                        dup_skip += 1
                        continue
                    seen.add(h)
                    s["hash"] = h
                    # 出题类样本按比例抽留 holdout（解题/写作等无固定答案形态不进 holdout）
                    to_hold = (s.get("form") == "problem_gen"
                               and rng.random() < args.holdout_ratio)
                    target = hold_files if to_hold else files
                    target[s["category"]].write(json.dumps(s, ensure_ascii=False) + "\n")
                    if to_hold:
                        hold_counts[s["category"]] += 1
                    else:
                        cat_counts[s["category"]] += 1
                    total_samples += 1
                tasks_done += 1
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
            "elapsed_s": round(time.time() - started), "category_counts": cat_counts,
            "holdout_counts": hold_counts, "holdout_ratio": args.holdout_ratio}
    with open(os.path.join(args.outdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    for f in list(files.values()) + list(hold_files.values()):
        f.close()
    print(json.dumps(meta, ensure_ascii=False))

    if args.smoke:
        for c in SHARE:
            path = os.path.join(args.outdir, f"{c}.jsonl")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    print("-" * 60)
                    print(f"[类别 {c} / form {rec.get('form')}]")
                    for m in rec["messages"]:
                        print(f"  [{m['role']}] {str(m['content'])[:200]}")
                    break


if __name__ == "__main__":
    main()
