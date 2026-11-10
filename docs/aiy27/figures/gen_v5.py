#!/usr/bin/env python3
"""AIY 27 PPT v5：编辑式「证据照片 + 象牙白抽象面板」10 页。

设计约束（photo-abstract-editorial 借用）：
- 照片/截图原样保留，不套壳、不滤镜；版面靠留白与细线分栏。
- 每页一个抽象标记，从本页数据本身长出来（圆环/刻度/比分条/点阵）。
- 象牙白 #F3F0E8 + 近黑 + 锈红；蓝/青/绿只做次级信息。
- 英文衬线标题 2-4 词，中文标题承担信息；正文 9-10.5pt。
- 数字只来自评测报告/训练日志，不写「提升显著」这类空话。

用法：.venv/bin/python docs/aiy27/figures/gen_v5.py
"""
import os

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "AIY27-PPT-v5.pptx")
ASSETS = os.path.join(HERE, "v5-assets")

PAPER = RGBColor(0xF3, 0xF0, 0xE8)
INK = RGBColor(0x18, 0x17, 0x15)
MUTED = RGBColor(0x6E, 0x68, 0x5D)
LIGHT = RGBColor(0x9B, 0x94, 0x87)
HAIR = RGBColor(0xD8, 0xD1, 0xC3)
BLUE = RGBColor(0x4F, 0x72, 0x96)
BLUE_LT = RGBColor(0xA9, 0xBC, 0xCC)
TEAL = RGBColor(0x6E, 0x9C, 0x96)
GREEN = RGBColor(0x7F, 0xA0, 0x7A)
RUST = RGBColor(0xB5, 0x52, 0x39)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SERIF = "Georgia"
SANS = "PingFang SC"
MONO = "Menlo"

SW, SH = Inches(13.333), Inches(7.5)
M = Inches(0.75)
CW = SW - 2 * M


def _font(run, size, bold=False, color=INK, name=SANS, italic=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {})
            rPr.append(e)
        e.set("typeface", name)


def txt(slide, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        ls=1.0, sa=0):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(sa)
        p.line_spacing = ls
        runs = para if isinstance(para, list) else [para]
        for r in runs:
            text, size, bold, color = r[:4]
            name = r[4] if len(r) > 4 else SANS
            italic = r[5] if len(r) > 5 else False
            run = p.add_run()
            run.text = text
            _font(run, size, bold, color, name, italic)
    return tb


def rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    return shp


def line(slide, x1, y1, x2, y2, color=HAIR, width=0.75):
    from pptx.enum.shapes import MSO_CONNECTOR
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color
    c.line.width = Pt(width)
    c.shadow.inherit = False
    return c


def circle_outline(slide, x, y, d, color=BLUE_LT, width=0.8):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    shp.fill.background()
    shp.line.color.rgb = color
    shp.line.width = Pt(width)
    shp.shadow.inherit = False
    return shp


def base(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, PAPER)
    return s


def kicker(s, text, page=None, x=M, total=10):
    rect(s, x, Inches(0.50), Inches(0.09), Inches(0.09), RUST)
    txt(s, x + Inches(0.17), Inches(0.47), Inches(8.6), Inches(0.20),
        [[(text, 7.5, True, RUST, MONO)]])
    if page:
        txt(s, SW - M - Inches(1.0), Inches(0.47), Inches(1.0), Inches(0.20),
            [[(f"{page:02d} / {total:02d}", 7.5, False, MUTED, MONO)]],
            align=PP_ALIGN.RIGHT)


def source(s, text, x=M, w=11.8):
    txt(s, x, Inches(7.14), Inches(w), Inches(0.20),
        [[(text, 6.8, False, MUTED, MONO)]])


def headline(s, lines, y=0.84, size=30):
    for i, l in enumerate(lines):
        txt(s, M, Inches(y + i * 0.54), Inches(11.6), Inches(0.55),
            [[(l, size, True, INK)]], ls=1.0)


def subline(s, text, y, size=9.8):
    txt(s, M, Inches(y), Inches(11.6), Inches(0.30),
        [[(text, size, False, MUTED)]], ls=1.15)


def label(s, x, y, text, color=RUST, w=4.0):
    txt(s, x, y, Inches(w), Inches(0.18), [[(text, 6.9, True, color, MONO)]])


def big(s, x, y, value, unit="", size=72, color=INK, w=4.6):
    runs = [(value, size, False, color, SERIF)]
    if unit:
        runs.append((" " + unit, 12, True, RUST, MONO))
    txt(s, x, y, Inches(w), Inches(size / 72.0 * 1.30 + 0.06), [runs], ls=1.0)


# ======================================================================
# P1 封面
# ======================================================================
def p1_cover(prs):
    s = base(prs)
    photo_w = Inches(4.6)
    s.shapes.add_picture(os.path.join(ASSETS, "cover-device-v5b.png"),
                         0, 0, width=photo_w)

    # 照片下方：证据说明，不压字在截图上
    label(s, Inches(0.55), Inches(5.66), "REAL DEVICE / 真机截图 · 非渲染")
    txt(s, Inches(0.55), Inches(5.88), Inches(3.8), Inches(0.24),
        [[("iPhone 18 Pro Max · 飞行模式 · 全程离线", 8.8, True, INK)]])
    txt(s, Inches(0.55), Inches(6.12), Inches(3.8), Inches(0.34),
        [[("截图 2026-11-06 20:30 · 1.7B Q4_K_M\n4 轮取后 3 轮 · 4K 上下文", 7.0, False, MUTED)]],
        ls=1.35)
    for i, c in enumerate([RGBColor(0x0A, 0x84, 0xFF), RGBColor(0x30, 0xD5, 0xC8),
                           RGBColor(0x34, 0xC7, 0x59), RGBColor(0xC9, 0xD1, 0xDE)]):
        rect(s, Inches(0.55) + Inches(0.20) * i, Inches(6.62), Inches(0.14), Inches(0.14), c)
    label(s, Inches(1.48), Inches(6.62), "APP PALETTE", color=LIGHT)

    x = Inches(5.15)
    kicker(s, "AIY 27 / FIELD REPORT", 1, x=x)
    txt(s, x, Inches(0.70), Inches(7.0), Inches(0.18),
        [[("高中组 PRO · 题目一 AI×科学工程（自定方向）", 6.8, True, MUTED, MONO)]])

    # 抽象标记：跑分圆环 + 四轮刻度 + 三条模型色带
    circle_outline(s, Inches(10.55), Inches(0.55), Inches(2.35), BLUE_LT, 0.9)
    for i in range(4):
        color = BLUE if i < 3 else HAIR
        rect(s, Inches(10.95) + Inches(0.20) * i, Inches(1.82), Inches(0.045),
             Inches(0.26), color)
    for i, (w, c) in enumerate([(1.75, BLUE), (1.45, TEAL), (1.10, GREEN)]):
        rect(s, Inches(11.05), Inches(2.28) + Inches(0.15) * i, Inches(w),
             Inches(0.05), c)

    txt(s, x, Inches(1.16), Inches(5.25), Inches(1.8),
        [[("POCKET", 34, False, INK, SERIF)],
         [("INTELLIGENCE", 34, False, INK, SERIF)]], ls=1.0)
    txt(s, x, Inches(2.60), Inches(5.25), Inches(0.50),
        [[("口袋里的 Agent 实验室", 23, True, INK)]])
    txt(s, x, Inches(3.14), Inches(5.25), Inches(0.30),
        [[("A local-first agent lab on a phone", 12.5, False, MUTED, SERIF, True)]])
    txt(s, x, Inches(3.60), Inches(5.30), Inches(0.64),
        [[("数据不出设备，美高课程特训；\n日历 / 提醒真的能用，一台 iPhone 跑起来。", 9.8, False, MUTED)]],
        ls=1.45)
    txt(s, x, Inches(4.52), Inches(5.30), Inches(0.58),
        [[("不是云端助手的缩小版，\n而是学生自己的本地 Agent 工作台。", 10.5, True, RUST)]],
        ls=1.45)

    stats = [("61.1", "tok/s", "18 Pro Max · 1.7B Q4_K_M"),
             ("0", "上传", "推理全程本机"),
             ("16/16", "真机自检", "13 场景 + 3 语音")]
    for i, (value, unit, note) in enumerate(stats):
        sx = x + Inches(1.80) * i
        txt(s, sx, Inches(5.42), Inches(1.72), Inches(0.48),
            [[(value, 22, False, INK, SERIF), (" " + unit, 7.5, False, RUST, MONO)]])
        txt(s, sx, Inches(5.92), Inches(1.72), Inches(0.20),
            [[(note, 7.0, False, MUTED)]])

    line(s, x, Inches(6.40), SW - M, Inches(6.40), HAIR, 0.6)
    txt(s, x, Inches(6.58), Inches(7.0), Inches(0.22),
        [[("团队：____________    演示人：____________    GitHub：mobile-llm-engine",
           8.2, False, MUTED, MONO)]])
    source(s, "模型口径：基于 Qwen3 继续训练 · 推理底座 llama.cpp（MIT）· 数字来自本机训练与真机日志",
           x=x, w=7.4)


# ======================================================================
# P2 问题
# ======================================================================
def p2_problem(prs):
    s = base(prs)
    kicker(s, "01 / PROBLEM", 2)
    headline(s, ["数据一旦离开设备，", "控制权就没了。"])
    subline(s, "国际学校 / 美高学生每天遇到的不是「AI 不好用」，而是「不敢用」和「没网用」。", 1.98)

    # 右上：信号衰减的抽象标记，最短一条锈红
    for i, w in enumerate([1.80, 1.50, 1.20, 0.90, 0.58]):
        y = Inches(1.08) + Inches(0.17) * i
        line(s, Inches(12.55) - Inches(w), y, Inches(12.55), y,
             RUST if i == 4 else BLUE_LT, 1.0 if i == 4 else 0.7)
    label(s, Inches(11.15), Inches(2.02), "DATA OUT", color=LIGHT, w=1.4)

    stats = [
        ("0", "云端助手断网可用性", "请求离开设备；断网即失效，数据已经出设备"),
        ("3.29万", "ZCode 事件被上传文件", "4.11 亿明文字符，项目连同修改历史打包上传"),
        ("15/15", "改前日期题全错", "模型没有「今天」锚点，只能靠心算瞎猜"),
    ]
    yy = 2.36
    for i, (v, lab, note) in enumerate(stats):
        big(s, M, Inches(yy), v, size=36, w=5.4)
        txt(s, M, Inches(yy + 0.68), Inches(5.4), Inches(0.22),
            [[(lab, 9.2, True, INK)]])
        txt(s, M, Inches(yy + 0.90), Inches(5.4), Inches(0.34),
            [[(note, 7.5, False, MUTED)]], ls=1.25)
        if i < 2:
            line(s, M, Inches(yy + 1.26), Inches(6.2), Inches(yy + 1.26), HAIR, 0.6)
        yy += 1.30

    rx = Inches(7.05)
    label(s, rx, Inches(3.62), "2026 公开事故（节选）")
    line(s, rx, Inches(3.84), Inches(12.55), Inches(3.84), INK, 0.8)
    items = [
        ("2026.04–06", "Claude Code 安全后门", "未经同意回传地域、身份标识等敏感数据", "求是网 / 工信部风险提示"),
        ("2026.09", "智谱 ZCode 传包风波", "3.29 万个文件、4.11 亿字符，连同修改历史上传", "36氪 / 掘金（企业函件）"),
        ("2026.08", "PROMPTPEEK 侧信道", "共享缓存可还原其他用户的提问内容", "NDSS 2025 论文"),
    ]
    yy = 3.98
    for i, (yr, title, detail, src) in enumerate(items):
        txt(s, rx, Inches(yy), Inches(1.10), Inches(0.18),
            [[(yr, 7.0, True, RUST, MONO)]])
        txt(s, rx + Inches(1.18), Inches(yy - 0.01), Inches(4.2), Inches(0.20),
            [[(title, 9.0, True, INK)]])
        txt(s, rx + Inches(1.18), Inches(yy + 0.21), Inches(4.2), Inches(0.34),
            [[(detail, 7.4, False, MUTED)]], ls=1.2)
        txt(s, rx + Inches(1.18), Inches(yy + 0.58), Inches(4.2), Inches(0.16),
            [[(src, 6.0, False, LIGHT, MONO)]])
        if i < 2:
            line(s, rx, Inches(yy + 0.80), Inches(12.55), Inches(yy + 0.80), HAIR, 0.6)
        yy += 0.92

    rect(s, M, Inches(6.34), Inches(0.06), Inches(0.58), RUST)
    txt(s, M + Inches(0.18), Inches(6.30), Inches(11.4), Inches(0.22),
        [[("目标用户：国际学校 / 美高在读学生 + 想学 AI 编排的初学者", 9.0, True, INK)]])
    txt(s, M + Inches(0.18), Inches(6.56), Inches(11.4), Inches(0.30),
        [[("我们要的不是更聪明的云端，而是能放在口袋里的控制权。", 13.5, True, RUST)]])
    source(s, "来源：2026 年公开报道（求是网 / 工信部 NVDB、36氪 / 掘金、NDSS 2025）· 用户调研")


# ======================================================================
# P3 方案
# ======================================================================
def p3_solution(prs):
    s = base(prs)
    kicker(s, "02 / SOLUTION", 3)
    headline(s, ["一句话，七步，", "日历里真的多了一条。"])
    subline(s, "从断网到写入，全程发生在手机本地；每一步都可复核。", 1.98)

    label(s, M, Inches(2.38), "用户原话 / 飞行模式")
    txt(s, M, Inches(2.60), Inches(11.2), Inches(0.42),
        [[("「家长会，明天下午三点，学校，约一小时」", 20, True, INK)]])
    line(s, M, Inches(3.12), Inches(12.55), Inches(3.12), HAIR, 0.7)

    steps = [
        ("01", "飞行模式", "手机彻底断网"),
        ("02", "本地推理", "1.7B 模型在手机里"),
        ("03", "工具调用", "输出标准 tool_call JSON"),
        ("04", "schema 校验", "参数不对直接拒绝"),
        ("05", "系统确认", "用户点「允许」才执行"),
        ("06", "EventKit 写入", "日历里真的多一条"),
        ("07", "回读校验", "写不进去就如实报错"),
    ]
    sx = M
    sw = Inches(1.66)
    for i, (num, title, detail) in enumerate(steps):
        if i:
            line(s, sx - Inches(0.10), Inches(3.42), sx - Inches(0.10), Inches(3.86), HAIR, 0.6)
        txt(s, sx, Inches(3.34), sw, Inches(0.26),
            [[(num, 12, True, RUST, MONO)]])
        txt(s, sx, Inches(3.62), sw, Inches(0.22),
            [[(title, 8.7, True, INK)]])
        txt(s, sx, Inches(3.84), sw - Inches(0.08), Inches(0.38),
            [[(detail, 6.8, False, MUTED)]], ls=1.2)
        sx += sw + Inches(0.08)
    line(s, M, Inches(4.34), Inches(12.55), Inches(4.34), HAIR, 0.7)

    features = [
        ("完全离线", "权重与推理都在手机，飞行模式可完整跑通。"),
        ("工具闭环", "不是聊天，是把事办成：日历 / 提醒真实写入系统。"),
        ("人确认", "写入前弹系统确认框，显示可读日期与过期警告。"),
    ]
    fx = M
    fw = Inches(3.90)
    for i, (title, detail) in enumerate(features):
        txt(s, fx, Inches(4.52), fw, Inches(0.24), [[(title, 11.2, True, INK)]])
        txt(s, fx, Inches(4.78), fw - Inches(0.25), Inches(0.50),
            [[(detail, 7.8, False, MUTED)]], ls=1.3)
        if i < 2:
            line(s, fx + fw - Inches(0.20), Inches(4.50), fx + fw - Inches(0.20), Inches(5.20), HAIR, 0.6)
        fx += fw + Inches(0.10)

    line(s, M, Inches(5.46), Inches(12.55), Inches(5.46), HAIR, 0.7)
    proof = [("16/16", "真机回归（含 3 语音）"),
             ("21.7s", "13 场景套件耗时"),
             ("1804 MB", "峰值内存"),
             ("42–79", "场景解码 tok/s")]
    px = M
    for i, (v, lab) in enumerate(proof):
        txt(s, px, Inches(5.60), Inches(2.80), Inches(0.34),
            [[(v, 19, False, RUST if i == 0 else INK, SERIF)]])
        txt(s, px, Inches(5.98), Inches(2.75), Inches(0.18),
            [[(lab, 7.2, False, MUTED)]])
        if i < 3:
            line(s, px + Inches(2.83), Inches(5.62), px + Inches(2.83), Inches(6.06), HAIR, 0.6)
        px += Inches(3.0)

    txt(s, M, Inches(6.48), Inches(11.6), Inches(0.28),
        [[("断网也能把事办成——这是云端助手给不了的体验。", 13, True, RUST)]])
    source(s, "来源：iOS 演示壳（EngineKit）真机流程 · 16/16 回归（13 场景 + 3 语音）· 2026-11-09 · PIPL：数据不出设备")


# ======================================================================
# P4 训练：1.7B 数学到顶 → CAS
# ======================================================================
def p4_training(prs):
    s = base(prs)
    kicker(s, "03 / TRAINING", 4)
    headline(s, ["训练到顶之后，", "我们把数学交给工具。"])
    subline(s, "1.7B 的数学容量有上限；继续堆数据没用，改用 CAS 做确定性计算。", 1.98)

    label(s, M, Inches(2.38), "数学 69 题 / 客观对拍 / 越高越好")
    rows = [
        ("SFT19 学术底模", 45, BLUE),
        ("SFT25 雅思 LoRA", 47, BLUE),
        ("SFT26 FRQ LoRA", 47, LIGHT),
        ("SFT27e CAS 工具", 58, RUST),
    ]
    bar_x = M + Inches(2.15)
    bar_w = Inches(3.55)
    yy = 2.66
    for i, (name, score, color) in enumerate(rows):
        txt(s, M, Inches(yy - 0.04), Inches(2.05), Inches(0.22),
            [[(name, 8.3, True, MUTED if color == LIGHT else INK)]])
        rect(s, bar_x, Inches(yy), bar_w, Inches(0.018), HAIR)
        rect(s, bar_x, Inches(yy - 0.02), bar_w * score / 69.0, Inches(0.058), color)
        txt(s, bar_x + bar_w + Inches(0.12), Inches(yy - 0.08), Inches(0.8), Inches(0.22),
            [[(str(score), 10.5, True, color if color != BLUE else INK, MONO)]])
        yy += 0.42
    txt(s, M, Inches(4.52), Inches(6.55), Inches(0.48),
        [[("SFT26 把 31 道真实 FRQ 训进 1.7B，仍是 47/69；\nSFT27e 改走 CAS 工具调用，+11 题。", 8.2, False, MUTED)]],
        ls=1.3)

    rx = Inches(7.30)
    label(s, rx, Inches(2.38), "从真题到验收 / 五步")
    steps = [
        ("01", "真题转化", "31 道 AP FRQ，官方评分标准逐题转写"),
        ("02", "教师合成", "云端大模型 + 配比拼装，12.78M tokens"),
        ("03", "符号验真", "SymPy 对拍抓 110 条错解，不进训练池"),
        ("04", "SFT 训练", "双卡 3 epochs；数据量不再是瓶颈"),
        ("05", "工具验收", "69 题客观集；CAS 路线 58/69"),
    ]
    yy = 2.68
    for i, (num, title, detail) in enumerate(steps):
        txt(s, rx, Inches(yy), Inches(0.40), Inches(0.22),
            [[(num, 9.5, True, RUST, MONO)]])
        txt(s, rx + Inches(0.46), Inches(yy - 0.02), Inches(4.9), Inches(0.22),
            [[(title, 9.4, True, INK)]])
        txt(s, rx + Inches(0.46), Inches(yy + 0.20), Inches(4.9), Inches(0.22),
            [[(detail, 7.2, False, MUTED)]])
        if i < 4:
            line(s, rx, Inches(yy + 0.48), Inches(12.55), Inches(yy + 0.48), HAIR, 0.6)
        yy += 0.58

    line(s, M, Inches(5.34), Inches(12.55), Inches(5.34), HAIR, 0.7)
    stats = [("12.78M", "学术训练 tokens（SFT19）"),
             ("31", "道真实 FRQ 进训练"),
             ("110", "条 SymPy 抓出错解"),
             ("47/69", "纯训练路线最高分")]
    sx = M
    for i, (v, lab) in enumerate(stats):
        txt(s, sx, Inches(5.48), Inches(2.85), Inches(0.36),
            [[(v, 20, False, INK, SERIF)]])
        txt(s, sx, Inches(5.88), Inches(2.80), Inches(0.20),
            [[(lab, 7.2, False, MUTED)]])
        if i < 3:
            line(s, sx + Inches(2.88), Inches(5.50), sx + Inches(2.88), Inches(5.96), HAIR, 0.6)
        sx += Inches(3.02)

    txt(s, M, Inches(6.48), Inches(11.7), Inches(0.30),
        [[("数据质量不是瓶颈，容量才是；让模型理解与列式，计算交给确定性工具。", 12.5, True, RUST)]])
    source(s, "来源：SFT19 / SFT25 / SFT26 / SFT27e 评测 · train/lab-notebook/训练线总览（2026-11-09）")


# ======================================================================
# P5 引擎与真机跑分
# ======================================================================
def p5_engine(prs):
    s = base(prs)
    kicker(s, "04 / ENGINE", 5)
    headline(s, ["同一套代码，", "0.6B / 1.7B 都装进 iPhone。"])
    subline(s, "EngineKit 全 Swift 封装 llama.cpp；模型、上下文、速度档都可换，代价写在界面上。", 1.98)

    big(s, M, Inches(2.34), "61.1", "tok/s", size=68, w=4.3)
    txt(s, M, Inches(3.36), Inches(4.4), Inches(0.22),
        [[("1.7B Q4_K_M · 18 Pro Max · 4K 上下文", 8.8, True, INK)]])
    line(s, M, Inches(3.66), Inches(4.35), Inches(3.66), HAIR, 0.7)
    txt(s, M, Inches(3.82), Inches(4.3), Inches(0.40),
        [[("1.90", 30, False, INK, SERIF), (" GB", 10, True, MUTED, MONO)]])
    txt(s, M, Inches(4.26), Inches(4.3), Inches(0.20),
        [[("峰值内存（4K 上下文）", 7.6, False, MUTED)]])
    txt(s, M, Inches(4.60), Inches(4.3), Inches(0.22),
        [[("4K / 8K / 16K / 32K", 8.5, True, INK, MONO)]])
    txt(s, M, Inches(4.84), Inches(4.35), Inches(0.40),
        [[("KV 约 0.44 / 0.88 / 1.75 / 3.5 GB；8GB 机型建议 ≤8K。", 7.2, False, MUTED)]],
        ls=1.25)

    tx = Inches(5.35)
    ty = 2.38
    txt(s, tx, Inches(ty), Inches(2.0), Inches(0.20),
        [[("档位", 7.0, True, MUTED, MONO)]])
    txt(s, tx + Inches(2.15), Inches(ty), Inches(1.05), Inches(0.20),
        [[("17 PM", 7.0, True, LIGHT, MONO)]], align=PP_ALIGN.RIGHT)
    txt(s, tx + Inches(3.30), Inches(ty), Inches(1.15), Inches(0.20),
        [[("18 PM", 7.0, True, LIGHT, MONO)]], align=PP_ALIGN.RIGHT)
    txt(s, tx + Inches(4.70), Inches(ty), Inches(1.25), Inches(0.20),
        [[("峰值(18)", 7.0, True, LIGHT, MONO)]], align=PP_ALIGN.RIGHT)
    line(s, tx, Inches(ty + 0.26), Inches(12.55), Inches(ty + 0.26), INK, 0.8)
    rows = [
        ("1.7B Q4_K_M", "38.5", "61.1", "1903 MB", True),
        ("1.7B Q5_K_M", "34.2", "56.5", "2054 MB", False),
        ("1.7B Q8_0", "27.3", "40.1", "2683 MB", False),
        ("0.6B Q5_K_M", "86.9", "100.5", "1187 MB", False),
        ("0.6B Q4_K_M", "89.0", "119.7", "1144 MB", False),
        ("0.6B IQ4_XS", "96.7", "121.1", "1109 MB", False),
    ]
    yy = ty + 0.36
    for i, (name, v17, v18, peak, hot) in enumerate(rows):
        txt(s, tx, Inches(yy), Inches(2.0), Inches(0.24),
            [[(name, 9.2, True, INK if hot else MUTED)]])
        txt(s, tx + Inches(2.15), Inches(yy), Inches(1.05), Inches(0.24),
            [[(v17, 9.2, False, MUTED, MONO)]], align=PP_ALIGN.RIGHT)
        txt(s, tx + Inches(3.30), Inches(yy - 0.03), Inches(1.15), Inches(0.28),
            [[(v18, 15 if hot else 12.5, hot, RUST if hot else INK, MONO)]],
            align=PP_ALIGN.RIGHT)
        txt(s, tx + Inches(4.70), Inches(yy + 0.03), Inches(1.25), Inches(0.20),
            [[(peak, 6.8, False, MUTED, MONO)]], align=PP_ALIGN.RIGHT)
        if i < 5:
            line(s, tx, Inches(yy + 0.33), Inches(12.55), Inches(yy + 0.33), HAIR, 0.6)
        yy += 0.42

    line(s, M, Inches(5.36), Inches(12.55), Inches(5.36), HAIR, 0.7)
    label(s, M, Inches(5.48), "MULTI-AGENT CAPACITY / 规划，待实测")
    caps = [
        ("8GB 机型", "2–3 个 0.6B Agent 同时在线；再开进入内存警戒。"),
        ("12GB 机型", "2 个 1.7B + 1 个 0.6B；记录峰值与被终止次数。"),
        ("OOM 门禁", "每次组合跑分都测「最多几个不 OOM」，超预算自动降档。"),
    ]
    cx = M + Inches(2.55)
    for i, (title, detail) in enumerate(caps):
        txt(s, cx, Inches(5.46), Inches(3.1), Inches(0.20),
            [[(title, 8.6, True, INK)]])
        txt(s, cx, Inches(5.68), Inches(3.1), Inches(0.46),
            [[(detail, 7.2, False, MUTED)]], ls=1.25)
        if i < 2:
            line(s, cx + Inches(3.20), Inches(5.46), cx + Inches(3.20), Inches(6.10), HAIR, 0.6)
        cx += Inches(3.35)

    txt(s, M, Inches(6.48), Inches(11.7), Inches(0.30),
        [[("18 Pro Max 上 1.7B 稳定 61.1 tok/s；向下兼容 0.6B，向上预留多 Agent 内存预算。",
           12.5, True, RUST)]])
    source(s, "口径：4 轮取后 3 轮均值 · 4K · 均衡档 · 峰值内存单轮最高；17 PM 为同协议对比（2026-11-03）")


# ======================================================================
# P6 拍照做题
# ======================================================================
def p6_math(prs):
    s = base(prs)
    kicker(s, "05 / FIELD NOTE — MATH MODE", 6)
    txt(s, M, Inches(0.78), Inches(5.6), Inches(1.1),
        [[("PHOTO IN,", 25, False, INK, SERIF)],
         [("PROOF OUT", 25, False, INK, SERIF)]], ls=1.0)
    txt(s, M, Inches(1.62), Inches(6.4), Inches(0.40),
        [[("拍照做题：公式识别 → 本地 CAS → 可复核答案。", 16.5, True, INK)]])
    txt(s, M, Inches(2.08), Inches(6.3), Inches(0.30),
        [[("Texo 20M 公式识别 + math.js，在手机上完成「看图 → 题意 → 计算」。", 9.0, False, MUTED)]])

    label(s, M, Inches(2.52), "INPUT / 题目图（示例）")
    s.shapes.add_picture(os.path.join(ASSETS, "formula-input-v5b.png"),
                         M + Inches(0.10), Inches(2.74), width=Inches(3.55))

    label(s, M, Inches(4.80), "OCR / LaTeX")
    txt(s, M, Inches(5.00), Inches(6.4), Inches(0.24),
        [[("\\lim_{x\\rarr0}\\frac{\\sin x}{x}", 10.5, False, INK, MONO)]])
    label(s, M, Inches(5.36), "题意 / PARSED")
    txt(s, M, Inches(5.56), Inches(6.5), Inches(0.24),
        [[("求 ((sin(x))/(x)) 在 x→0 时的极限。", 9.8, False, INK, MONO)]])
    line(s, M, Inches(5.94), Inches(6.35), Inches(5.94), HAIR, 0.7)
    label(s, M, Inches(6.04), "ANSWER / math.js 本机计算")
    big(s, M, Inches(6.20), "1", size=40, color=RUST, w=1.2)
    txt(s, M, Inches(6.82), Inches(6.2), Inches(0.18),
        [[("数学段单独切 SFT27e；助理段仍用领队 + 工人。", 7.5, False, MUTED)]])

    rx = Inches(7.30)
    line(s, rx, Inches(1.10), rx + Inches(2.85), Inches(1.10), INK, 1.0)
    line(s, rx, Inches(1.30), rx + Inches(2.85), Inches(1.30), INK, 0.6)
    line(s, rx, Inches(1.74), rx + Inches(0.10), Inches(1.74), TEAL, 1.0)
    line(s, rx + Inches(0.10), Inches(1.74), rx + Inches(0.42), Inches(1.42), TEAL, 1.0)
    line(s, rx + Inches(0.42), Inches(1.42), rx + Inches(0.90), Inches(1.42), TEAL, 1.0)
    for i, c in enumerate([BLUE, BLUE, RUST, BLUE, BLUE]):
        rect(s, rx + Inches(2.20) + Inches(0.16) * i, Inches(1.52), Inches(0.045),
             Inches(0.30), c)

    stats = [("58/69", "数学端到端", "84.1% · SFT27e"),
             ("69/69", "工具发射", "schema 全通过"),
             ("186ms", "公式识别（热）", "18 Pro Max"),
             ("18/18", "Mac 对拍", "与 Python 逐字一致")]
    for i, (value, lab, note) in enumerate(stats):
        col, row = i % 2, i // 2
        sx = rx + Inches(2.15) * col
        sy = 2.56 + 1.02 * row
        txt(s, sx, Inches(sy), Inches(2.05), Inches(0.44),
            [[(value, 23, False, INK, SERIF)]])
        txt(s, sx, Inches(sy + 0.45), Inches(2.05), Inches(0.20),
            [[(lab, 8.4, True, INK)]])
        txt(s, sx, Inches(sy + 0.66), Inches(2.05), Inches(0.20),
            [[(note, 7.0, False, MUTED)]])

    line(s, rx, Inches(5.02), Inches(12.55), Inches(5.02), HAIR, 0.6)
    txt(s, rx, Inches(5.18), Inches(4.9), Inches(0.58),
        [[("一张照片，三个本机步骤：\n识别公式 → 转成题意 → 调用 CAS。", 10, False, MUTED)]],
        ls=1.45)
    txt(s, rx, Inches(6.02), Inches(4.9), Inches(0.30),
        [[("没有网络请求，也没有把题目发给云端。", 10.5, True, RUST)]])
    source(s, "来源：Texo 18 图对拍（2026-11-09）· SFT27e 69 题端到端评测 · iPhone 18 Pro Max 真机自检")


# ======================================================================
# P7 工具调用
# ======================================================================
def p7_tools(prs):
    s = base(prs)
    kicker(s, "06 / TEST 01", 7)
    headline(s, ["40 道工具题，", "40/40 全部正确发射。"])
    subline(s, "命题书要求「用测试证明有没有用」——每次工具调用都落成 case 文件。", 1.98)

    big(s, M, Inches(2.32), "40/40", size=68, w=5.4)
    txt(s, M, Inches(3.58), Inches(5.4), Inches(0.24),
        [[("tool_call 正确发射", 10.0, True, INK)]])
    txt(s, M, Inches(3.84), Inches(5.4), Inches(0.34),
        [[("1.7B Q5/Q4 双档 · 30 条训练分布 + 10 条泛化", 7.6, False, MUTED)]], ls=1.2)
    line(s, M, Inches(4.22), Inches(6.4), Inches(4.22), HAIR, 0.7)
    for i, (v, lab) in enumerate([("100%", "schema 校验通过"), ("100%", "JSON 解析成功")]):
        sx = M + Inches(2.85) * i
        txt(s, sx, Inches(4.34), Inches(2.7), Inches(0.34),
            [[(v, 22, False, RUST if i == 0 else INK, SERIF)]])
        txt(s, sx, Inches(4.72), Inches(2.65), Inches(0.20),
            [[(lab, 7.6, False, MUTED)]])

    txt(s, M, Inches(5.28), Inches(6.4), Inches(0.24),
        [[("TOOLS / 白名单", 6.9, True, RUST, MONO)]])
    txt(s, M, Inches(5.50), Inches(6.5), Inches(0.44),
        [[("add_calendar_event · add_reminder · translate\nsummarize · clarify", 8.0, False, INK, MONO)]],
        ls=1.35)
    txt(s, M, Inches(6.00), Inches(6.4), Inches(0.22),
        [[("schema 必填参数 + 时间正则；白名单外直接拒绝；写入前人工确认。", 7.4, False, MUTED)]])

    rx = Inches(7.30)
    label(s, rx, Inches(2.34), "40 CASES / 一格一题")
    gx, gy = 7.30, 2.62
    cell, gap = 0.30, 0.18
    for i in range(40):
        col, row = i % 8, i // 8
        color = BLUE if i < 30 else TEAL
        rect(s, Inches(gx + col * (cell + gap)), Inches(gy + row * (cell + gap)),
             Inches(cell), Inches(cell), color)
    rect(s, rx, Inches(4.98), Inches(0.10), Inches(0.10), BLUE)
    txt(s, rx + Inches(0.16), Inches(4.94), Inches(1.7), Inches(0.18),
        [[("30 训练分布", 6.8, False, MUTED, MONO)]])
    rect(s, rx + Inches(1.75), Inches(4.98), Inches(0.10), Inches(0.10), TEAL)
    txt(s, rx + Inches(1.91), Inches(4.94), Inches(1.5), Inches(0.18),
        [[("10 泛化", 6.8, False, MUTED, MONO)]])

    line(s, rx, Inches(5.32), Inches(12.55), Inches(5.32), HAIR, 0.6)
    txt(s, rx, Inches(5.46), Inches(5.2), Inches(0.44),
        [[("不是「感觉能用」，是逐题可复核；\n失败样例也保留，能回放。", 9.0, False, MUTED)]],
        ls=1.35)
    txt(s, rx, Inches(6.12), Inches(5.2), Inches(0.30),
        [[("40/40 不是全场景全对，是这套 40 题全对。", 9.0, True, RUST)]])
    source(s, "来源：SFT19 评测（40 题，temp 0.7）· SFT3 工具遵循率专项 · 16/16 真机回归")


# ======================================================================
# P8 日期诚实
# ======================================================================
def p8_dates(prs):
    s = base(prs)
    kicker(s, "07 / TEST 02", 8)
    headline(s, ["日期题，", "从 15/15 全错到 58/60。"])
    subline(s, "改前 15 题全错；补日期表后把验收集扩到 60 题，再训边界。", 1.98)

    big(s, M, Inches(2.32), "58/60", size=68, w=5.4)
    txt(s, M, Inches(3.58), Inches(5.4), Inches(0.24),
        [[("日期题精确匹配 · SFT20d", 10.0, True, INK)]])
    txt(s, M, Inches(3.84), Inches(5.4), Inches(0.34),
        [[("上一版 SFT20c 93.3%；这一版 96.7%。", 7.6, False, MUTED)]])

    rows = [("96.7%", "60 题日期集（SFT20d）"),
            ("16/16", "边界题：闰日 / 跨年 / 跨月 / 小时进位"),
            ("8/8", "工人四工种回归")]
    yy = 4.22
    for i, (v, lab) in enumerate(rows):
        txt(s, M, Inches(yy), Inches(1.55), Inches(0.30),
            [[(v, 19, False, RUST if i == 0 else INK, SERIF)]])
        txt(s, M + Inches(1.55), Inches(yy + 0.06), Inches(4.6), Inches(0.22),
            [[(lab, 8.0, False, MUTED)]])
        if i < 2:
            line(s, M, Inches(yy + 0.36), Inches(6.4), Inches(yy + 0.36), HAIR, 0.6)
        yy += 0.46

    txt(s, M, Inches(5.70), Inches(6.4), Inches(0.22),
        [[("日期表由引擎注入，不让模型心算日历。", 7.6, False, MUTED)]])
    txt(s, M, Inches(6.36), Inches(6.4), Inches(0.30),
        [[("剩下的 2 题写进限制，不假装 100%。", 12.5, True, RUST)]])

    rx = Inches(7.30)
    label(s, rx, Inches(2.34), "60 题 / 一格一题 / 58 对 2 错")
    gx, gy = 7.30, 2.62
    tw, th, gpx, gpy = 0.14, 0.30, 0.18, 0.12
    for i in range(60):
        col, row = i % 10, i // 10
        color = RUST if i >= 58 else INK
        rect(s, Inches(gx + col * (tw + gpx)), Inches(gy + row * (th + gpy)),
             Inches(tw), Inches(th), color)
    label(s, rx, Inches(5.26), "仍错 2 题 / 写进产品限制", color=RUST)
    txt(s, rx, Inches(5.48), Inches(5.2), Inches(0.22),
        [[("2027-02-29 不存在 → 应滚到 2028", 7.8, False, MUTED, MONO)]])
    txt(s, rx, Inches(5.70), Inches(5.2), Inches(0.22),
        [[("23:30 + 3h 跨天 → 只加了 1h", 7.8, False, MUTED, MONO)]])
    line(s, rx, Inches(6.04), Inches(12.55), Inches(6.04), HAIR, 0.6)
    txt(s, rx, Inches(6.18), Inches(5.2), Inches(0.30),
        [[("能答的答，不能答的交给确认框。", 9.2, True, INK)]])
    source(s, "来源：SFT20b / SFT20c / SFT20d 日期评测（60 题，2026-11-08）· 训练线总览")


# ======================================================================
# P9 风险与人
# ======================================================================
def p9_risk(prs):
    s = base(prs)
    kicker(s, "08 / RISK & HUMAN", 9)
    headline(s, ["AI 判断错了，", "产品怎么办？"])
    subline(s, "命题书完成重点：怎样提醒使用者、由谁确认和处理。", 1.98)

    cols = [M, Inches(4.10), Inches(10.20)]
    label(s, cols[0], Inches(2.36), "风险")
    label(s, cols[1], Inches(2.36), "产品怎么提醒")
    label(s, cols[2], Inches(2.36), "谁确认 / 处理")
    line(s, M, Inches(2.60), Inches(12.55), Inches(2.60), INK, 0.8)

    risks = [
        ("日期 / 事实幻觉", "结果卡标注「不确定」；schema 拦截占位符，不执行写入。", "使用者本人"),
        ("时间 / 地点写错", "系统确认框显示可读日期与过期警告；确认后才写入。", "使用者本人"),
        ("模型编造工具", "白名单拒绝，返回失败原因并记日志；用户可见失败。", "使用者本人"),
        ("模型答不上来", "明确说「不知道」，不硬编；保留原始输出。", "使用者本人"),
        ("导入未知 GGUF", "导入前免责：App 只提供本地推理环境，不分发模型。", "使用者本人"),
    ]
    yy = 2.74
    for i, (risk, how, who) in enumerate(risks):
        txt(s, cols[0], Inches(yy), Inches(3.2), Inches(0.40),
            [[(risk, 9.2, True, INK)]])
        txt(s, cols[1], Inches(yy), Inches(5.9), Inches(0.40),
            [[(how, 8.0, False, MUTED)]], ls=1.2)
        txt(s, cols[2], Inches(yy), Inches(2.2), Inches(0.40),
            [[(who, 8.0, True, INK)]])
        if i < 4:
            line(s, M, Inches(yy + 0.44), Inches(12.55), Inches(yy + 0.44), HAIR, 0.6)
        yy += 0.52

    rect(s, M, Inches(5.56), Inches(0.06), Inches(0.62), RUST)
    txt(s, M + Inches(0.18), Inches(5.52), Inches(11.4), Inches(0.30),
        [[("红线：AI 只提供建议与结构化结果，最终决定权永远在人。", 17, True, INK)]])
    txt(s, M + Inches(0.18), Inches(5.94), Inches(11.4), Inches(0.34),
        [[("App Store：不下载可执行代码 · 模型仅本地推理 · 权限最小化 · 隐私政策 · 无账号与统计 SDK",
           7.6, False, MUTED)]], ls=1.2)
    txt(s, M + Inches(0.18), Inches(6.24), Inches(11.4), Inches(0.34),
        [[("权限只在工具执行时申请；拒绝授权则功能降级，不影响本地对话。", 7.2, False, MUTED)]])
    txt(s, M, Inches(6.56), Inches(11.9), Inches(0.22),
        [[("当前限制：1.7B 复杂推理有限 · 工具只覆盖日历 / 提醒 / 翻译 / 摘要 · Android 未覆盖 · 日期 2/60 错 · 数学 11/69 错",
           6.9, False, MUTED)]])
    source(s, "来源：ToolKit 白名单 / schema · 16/16 真机回归 · 日期 60 题 · App Store Review Guidelines 2.5.2 / 5.1.1")


# ======================================================================
# P10 团队与路线
# ======================================================================
def p10_team(prs):
    s = base(prs)
    kicker(s, "09 / TEAM & NEXT", 10)
    headline(s, ["一个人 + 一套 AI 工具链，", "把全栈跑通。"])
    subline(s, "命题书硬性覆盖项 + 接下来的路线；训练队列与发布门禁都写进仓库。", 1.98)

    label(s, M, Inches(2.36), "团队分工（按实际填写）")
    team = ["引擎运行时（EngineKit）", "模型训练与数据合成",
            "iOS App 与演示", "评测与回归", "产品与测试"]
    yy = 2.58
    for line_ in team:
        txt(s, M, Inches(yy), Inches(2.4), Inches(0.20),
            [[(line_, 8.3, False, INK)]])
        line(s, M + Inches(2.45), Inches(yy + 0.16), M + Inches(5.95), Inches(yy + 0.16), HAIR, 0.6)
        yy += 0.25

    label(s, M, Inches(3.96), "AI 工具使用说明")
    ai_lines = [
        "训练数据：云端教师大模型合成 + SymPy 后验 + 锚点/格式质检",
        "真题转化：官方 CodeBuddy CLI 逐题切题与评分标准转写",
        "开发辅助：编码/文档 AI 协作；对话与提示词可导出复查",
    ]
    yy = 4.18
    for line_ in ai_lines:
        txt(s, M, Inches(yy), Inches(7.0), Inches(0.20),
            [[(line_, 7.8, False, MUTED)]])
        yy += 0.22

    label(s, M, Inches(4.96), "第三方资源")
    third = [
        "llama.cpp（MIT）· Qwen3（Apache 2.0）· sherpa-onnx",
        "Texo 公式识别权重（AGPL-3.0，本仓库同许可）",
        "iOS EventKit / SwiftUI / Vision 系统框架",
    ]
    yy = 5.18
    for line_ in third:
        txt(s, M, Inches(yy), Inches(7.0), Inches(0.20),
            [[(line_, 7.8, False, MUTED)]])
        yy += 0.22

    txt(s, M, Inches(5.94), Inches(7.1), Inches(0.22),
        [[("模型口径：基于 Qwen3 继续训练，不自称自研；提交物 = 10 页 PPT + ≤8 分钟真机 Demo。",
           7.4, True, INK)]], ls=1.2)

    rx = Inches(8.10)
    label(s, rx, Inches(2.36), "路线（已实现 / 进行中 / 规划）")
    roadmap = [
        ("01", "SFT27e CAS 已采用", "58/69，Q5/Q4 已量化", False),
        ("02", "4B 旗舰", "暂缓，等排期；1.7B 容量到顶", False),
        ("03", "iOS 演示壳", "真机 16/16；TestFlight 准备中", False),
        ("04", "本地多 Agent 编排", "Planner + Worker + Verifier；内存预算 + OOM 门禁", True),
        ("05", "Android", "规划中，端侧多平台", False),
    ]
    yy = 2.62
    for i, (num, title, detail, hot) in enumerate(roadmap):
        if hot:
            rect(s, rx - Inches(0.14), Inches(yy - 0.02), Inches(0.05), Inches(0.52), RUST)
        txt(s, rx, Inches(yy), Inches(0.45), Inches(0.20),
            [[(num, 9.2, True, RUST if hot else LIGHT, MONO)]])
        txt(s, rx + Inches(0.48), Inches(yy - 0.01), Inches(4.0), Inches(0.20),
            [[(title, 9.0, True, INK)]])
        txt(s, rx + Inches(0.48), Inches(yy + 0.20), Inches(3.95), Inches(0.30),
            [[(detail, 6.9, False, MUTED)]], ls=1.2)
        if i < 4:
            line(s, rx, Inches(yy + 0.54), Inches(12.55), Inches(yy + 0.54), HAIR, 0.6)
        yy += 0.64

    line(s, M, Inches(6.28), Inches(12.55), Inches(6.28), HAIR, 0.7)
    txt(s, M, Inches(6.40), Inches(11.6), Inches(0.20),
        [[("GitHub：github.com/fanyifan090409-dev/mobile-llm-engine · 回归 / 跑分 / 训练日志随仓库提供",
           7.0, False, MUTED, MONO)]])
    txt(s, M, Inches(6.64), Inches(11.6), Inches(0.30),
        [[("把 AI 从云端搬进口袋，把编排权交给学生。", 12.5, True, RUST)]])
    source(s, "来源：项目仓库 · 训练 / 评测日志 · 第三方许可证（MIT / Apache 2.0 / AGPL-3.0）")


def main():
    prs = Presentation()
    prs.slide_width = SW
    prs.slide_height = SH
    prs.core_properties.title = "Pocket Intelligence — 口袋里的 Agent 实验室"
    prs.core_properties.author = "樊一凡"
    prs.core_properties.subject = "AIY 27 高中组 PRO · 题目一 AI×科学工程（自定方向）"
    p1_cover(prs)
    p2_problem(prs)
    p3_solution(prs)
    p4_training(prs)
    p5_engine(prs)
    p6_math(prs)
    p7_tools(prs)
    p8_dates(prs)
    p9_risk(prs)
    p10_team(prs)
    prs.save(OUT)
    print("saved", OUT, "slides", len(prs.slides))


if __name__ == "__main__":
    main()
