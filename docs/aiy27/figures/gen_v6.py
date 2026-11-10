#!/usr/bin/env python3
"""AIY 27 PPT v6：产品发布级重做（10 页）。

视觉系统：
- 象牙白 #F7F3EA + 深海军蓝 #0B1B2B + 电蓝 #1E6BFF + 薄荷 #2FBFB0 + 锈红 #B24A32。
- 深色面板只做分区，不做整页暗底；真实设备卡 + 真实数据图 + 深色代码面板。
- 中文 PingFang SC；英文/数字 Helvetica Neue；代码 Menlo。
- 所有数字来自评测报告/训练日志；WPS 导出 PDF 后逐页目检。
"""
import os

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "AIY27-PPT-v6.pptx")
A = os.path.join(HERE, "v6-assets")
OLD = os.path.join(HERE, "v5-assets")

IVORY = RGBColor(0xF7, 0xF3, 0xEA)
PAPER2 = RGBColor(0xEF, 0xE8, 0xDB)
NAVY = RGBColor(0x0B, 0x1B, 0x2B)
NAVY2 = RGBColor(0x13, 0x29, 0x3D)
BLUE = RGBColor(0x1E, 0x6B, 0xFF)
MINT = RGBColor(0x2F, 0xBF, 0xB0)
ICE = RGBColor(0xDC, 0xE8, 0xF5)
INK = RGBColor(0x0E, 0x11, 0x16)
GRAY = RGBColor(0x6E, 0x76, 0x80)
LIGHT = RGBColor(0x9A, 0xA3, 0xAD)
LINE = RGBColor(0xD9, 0xD2, 0xC5)
RUST = RGBColor(0xB2, 0x4A, 0x32)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

CN = "PingFang SC"
EN = "Helvetica Neue"
MONO = "Menlo"

SW, SH = Inches(13.333), Inches(7.5)
M = Inches(0.75)
CW = SW - 2 * M


def _font(run, size, bold=False, color=INK, name=CN, italic=False, tracking=None):
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
    if tracking is not None:
        rPr.set("spc", str(int(tracking)))


def txt(slide, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        ls=1.0, sa=0, wrap=False):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.auto_size = None
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
            name = r[4] if len(r) > 4 else CN
            italic = r[5] if len(r) > 5 else False
            tracking = r[6] if len(r) > 6 else None
            run = p.add_run()
            run.text = text
            _font(run, size, bold, color, name, italic, tracking)
    return tb


def rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75, radius=None):
    shape = MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape, x, y, w, h)
    if radius is not None:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
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


def line(slide, x1, y1, x2, y2, color=LINE, width=0.75):
    from pptx.enum.shapes import MSO_CONNECTOR
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color
    c.line.width = Pt(width)
    c.shadow.inherit = False
    return c


def circle_outline(slide, x, y, d, color=BLUE, width=1.0, fill=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = color
    shp.line.width = Pt(width)
    shp.shadow.inherit = False
    return shp


def base(prs, dark=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, NAVY if dark else IVORY)
    return s


def kicker(s, text, page=None, x=M, color=BLUE, dark=False):
    rect(s, x, Inches(0.52), Inches(0.08), Inches(0.08), color)
    txt(s, x + Inches(0.16), Inches(0.48), Inches(8.8), Inches(0.18),
        [[(text, 7.5, True, color, EN, False, 160)]])
    if page:
        txt(s, SW - M - Inches(1.0), Inches(0.48), Inches(1.0), Inches(0.18),
            [[(f"{page:02d} / 10", 7.5, False, LIGHT if dark else GRAY, EN)]],
            align=PP_ALIGN.RIGHT)


def source(s, text, x=M, w=11.8, dark=False):
    txt(s, x, Inches(7.14), Inches(w), Inches(0.18),
        [[(text, 6.4, False, LIGHT if dark else GRAY, MONO)]])


def headline(s, lines, y=0.82, size=29, width=11.6):
    for i, l in enumerate(lines):
        txt(s, M, Inches(y + i * 0.50), Inches(width), Inches(0.52),
            [[(l, size, True, INK)]], ls=1.0)


def lead(s, text, y, w=11.4, color=GRAY, size=10.2):
    txt(s, M, Inches(y), Inches(w), Inches(0.30),
        [[(text, size, False, color)]], ls=1.15, wrap=True)


def eyebrow(s, text, x, y, color=BLUE, w=4.0):
    from pptx.util import Length
    if not isinstance(y, Length):
        y = Inches(y)
    txt(s, x, y, Inches(w), Inches(0.18),
        [[(text, 7.0, True, color, EN, False, 180)]])


def big_num(s, x, y, value, unit="", size=100, color=INK, w=5.2):
    runs = [(value, size, False, color, EN)]
    if unit:
        runs.append((" " + unit, 12, False, BLUE, EN))
    txt(s, x, y, Inches(w), Inches(size / 72.0 * 1.10), [runs], ls=0.95)


def rule(s, x, y, w, color=LINE, width=0.8):
    line(s, x, y, x + w, y, color, width)


def panel_bg(s, name, x, y, w, h):
    """深色分区统一用背景图：渐变 + 弥散光 + 细环 + 颗粒，避免纯色板发闷。"""
    s.shapes.add_picture(os.path.join(A, name), x, y, width=w, height=h)


# ======================================================================
# P1 封面
# ======================================================================
def p1(prs):
    s = base(prs)
    # 右侧深色面板（背景图带弥散光与细环，圆环已烘焙进图）
    panel_bg(s, "bg-cover.jpg", Inches(7.35), 0, Inches(5.983), SH)

    # 真机屏幕卡
    s.shapes.add_picture(os.path.join(A, "device-tile.png"),
                         Inches(8.55), Inches(0.62), width=Inches(3.95))
    txt(s, Inches(8.55), Inches(5.38), Inches(3.95), Inches(0.20),
        [[("REAL DEVICE / iPhone 18 Pro Max", 7.0, True, ICE, EN, False, 120)]])
    txt(s, Inches(8.55), Inches(5.62), Inches(3.95), Inches(0.22),
        [[("飞行模式 · 20:30 · Q4_K_M · 4K", 7.4, False, RGBColor(0x8F, 0xA8, 0xC2), EN)]])
    txt(s, Inches(11.65), Inches(0.48), Inches(0.9), Inches(0.18),
        [[("01 / 10", 7.5, False, RGBColor(0x8F, 0xA8, 0xC2), EN)]], align=PP_ALIGN.RIGHT)

    # 左侧文字
    kicker(s, "AIY 27 / HIGH SCHOOL PRO", x=M)
    txt(s, M, Inches(0.78), Inches(6.2), Inches(0.18),
        [[("题目一 · AI × 科学工程（自定方向）", 7.2, False, GRAY, CN)]])

    eyebrow(s, "POCKET INTELLIGENCE", M, 1.38, GRAY, 5.0)
    txt(s, M, Inches(1.68), Inches(6.4), Inches(1.55),
        [[("口袋里的", 46, True, INK)],
         [("Agent 实验室", 46, True, INK)]], ls=1.02)
    txt(s, M, Inches(3.28), Inches(6.3), Inches(0.30),
        [[("A local-first agent lab on a phone", 12.5, False, GRAY, EN)]])
    txt(s, M, Inches(3.76), Inches(5.9), Inches(0.72),
        [[("一台 iPhone，跑完整个 Agent 闭环。\n不联网，也不把数据交出去。", 13.0, False, INK)]],
        ls=1.45)
    rule(s, M, Inches(4.56), Inches(5.7), LINE, 0.8)

    stats = [("61.1", "tok/s", "18 Pro Max · 1.7B Q4"),
             ("0", "上传", "推理全程本机"),
             ("16/16", "真机自检", "13 场景 + 3 语音")]
    for i, (v, u, lab) in enumerate(stats):
        x = M + Inches(1.90) * i
        txt(s, x, Inches(4.84), Inches(1.82), Inches(0.44),
            [[(v, 30, False, INK, EN), (" " + u, 8.0, True, BLUE, EN)]], ls=0.95)
        txt(s, x, Inches(5.32), Inches(1.80), Inches(0.20),
            [[(lab, 7.4, False, GRAY, CN)]])

    txt(s, M, Inches(6.22), Inches(6.0), Inches(0.24),
        [[("樊一凡 · 队长", 8.6, True, INK), ("      GitHub：mobile-llm-engine", 7.6, False, GRAY, MONO)]])
    txt(s, M, Inches(6.50), Inches(6.2), Inches(0.22),
        [[("模型口径：基于 Qwen3 继续训练 · 推理底座 llama.cpp（MIT）", 6.6, False, GRAY, CN)]])
    source(s, "资料：本机训练日志 / 真机跑分 / 16/16 回归 · 2026-11", w=11.8)


# ======================================================================
# P2 问题
# ======================================================================
def p2(prs):
    s = base(prs)
    kicker(s, "01 / THE PROBLEM", 2)
    headline(s, ["数据一旦离开设备，", "控制权就没了。"], y=0.84, size=30)
    lead(s, "国际学校 / 美高学生每天遇到的不是「AI 不好用」，而是「不敢用」和「没网用」。", 2.02, 7.2)

    big_num(s, M, Inches(2.62), "3.29万", size=92, color=INK, w=6.2)
    txt(s, M, Inches(4.18), Inches(6.2), Inches(0.24),
        [[("个文件，连同修改历史被打包上传", 10.0, True, INK)]])
    txt(s, M, Inches(4.48), Inches(6.2), Inches(0.40),
        [[("ZCode 事件 · 4.11 亿明文字符 · 2026.09", 7.8, False, GRAY, CN)]], ls=1.25)
    rule(s, M, Inches(5.02), Inches(6.0), LINE, 0.8)
    txt(s, M, Inches(5.22), Inches(6.0), Inches(0.62),
        [[("断网的那一刻，云端助手就消失了。\n数据已经离开设备，控制权也是。", 14.5, True, BLUE)]],
        ls=1.35)
    txt(s, M, Inches(6.08), Inches(6.0), Inches(0.20),
        [[("改前日期题 15/15 全错 · 模型没有「今天」锚点", 8.2, False, GRAY, CN)]])

    # 右侧深色面板
    panel_bg(s, "bg-problem.jpg", Inches(7.85), Inches(0.86), Inches(4.73), Inches(5.72))
    txt(s, Inches(8.15), Inches(1.12), Inches(4.1), Inches(0.18),
        [[("2026 / FIELD NOTES", 7.0, True, RGBColor(0x8F, 0xA8, 0xC2), EN, False, 160)]])
    txt(s, Inches(8.15), Inches(1.48), Inches(4.1), Inches(1.05),
        [[("0%", 66, False, WHITE, EN)]], ls=0.9)
    txt(s, Inches(8.15), Inches(2.48), Inches(4.1), Inches(0.20),
        [[("云端助手断网可用性", 8.2, True, ICE, CN)]])
    rule(s, Inches(8.15), Inches(2.86), Inches(4.05), RGBColor(0x2A, 0x44, 0x5C), 0.8)

    items = [
        ("2026.04–06", "Claude Code 安全后门", "未经同意回传地域、身份标识等敏感数据", "求是网 / 工信部"),
        ("2026.09", "智谱 ZCode 传包风波", "3.29 万个文件、4.11 亿字符，连同修改历史上传", "36氪 / 掘金"),
        ("2026.08", "PROMPTPEEK 侧信道", "共享缓存可还原其他用户的提问内容", "NDSS 2025"),
    ]
    y = 3.04
    for i, (d, t, det, src) in enumerate(items):
        txt(s, Inches(8.15), Inches(y), Inches(1.05), Inches(0.16),
            [[(d, 6.6, True, RGBColor(0x8F, 0xA8, 0xC2), MONO)]])
        txt(s, Inches(9.30), Inches(y - 0.01), Inches(3.0), Inches(0.20),
            [[(t, 8.6, True, WHITE, CN)]])
        txt(s, Inches(9.30), Inches(y + 0.20), Inches(2.95), Inches(0.36),
            [[(det, 7.0, False, RGBColor(0xB9, 0xC7, 0xD6), CN)]], ls=1.2, wrap=True)
        txt(s, Inches(9.30), Inches(y + 0.62), Inches(2.95), Inches(0.16),
            [[(src, 5.8, False, RGBColor(0x76, 0x8A, 0x9E), EN)]])
        if i < 2:
            line(s, Inches(8.15), Inches(y + 0.88), Inches(12.25), Inches(y + 0.88),
                 RGBColor(0x2A, 0x44, 0x5C), 0.6)
        y += 0.98

    txt(s, M, Inches(6.55), Inches(11.6), Inches(0.30),
        [[("我们要的不是更聪明的云端，而是能放在口袋里的控制权。", 12.5, True, RUST)]])
    source(s, "来源：2026 公开报道（求是网 / 工信部 NVDB、36氪 / 掘金、NDSS 2025）· 本项目评测")


# ======================================================================
# P3 方案
# ======================================================================
def p3(prs):
    s = base(prs)
    kicker(s, "02 / THE LOOP", 3)
    headline(s, ["一句话，七步，", "日历里真的多了一条。"], y=0.82, size=29)
    lead(s, "「家长会，明天下午三点，学校，约一小时。」飞行模式下，全部在本机完成。", 1.94, 11.2)

    steps = [
        ("01", "飞行模式", "彻底断网"),
        ("02", "本地推理", "1.7B 模型"),
        ("03", "工具调用", "tool_call JSON"),
        ("04", "schema", "参数校验"),
        ("05", "系统确认", "用户点允许"),
        ("06", "EventKit", "真实写入"),
        ("07", "回读", "失败如实报错"),
    ]
    line(s, M, Inches(2.72), Inches(12.58), Inches(2.72), LINE, 1.0)
    for i, (num, name, det) in enumerate(steps):
        x = M + Inches(1.70) * i
        rect(s, x, Inches(2.68), Inches(0.08), Inches(0.08), BLUE)
        txt(s, x, Inches(2.88), Inches(1.55), Inches(0.18),
            [[(num, 7.2, True, BLUE, MONO)]])
        txt(s, x, Inches(3.10), Inches(1.55), Inches(0.22),
            [[(name, 9.0, True, INK, CN)]])
        txt(s, x, Inches(3.34), Inches(1.50), Inches(0.34),
            [[(det, 6.8, False, GRAY, CN)]], ls=1.2)

    # 左：真机 VS Code 截图（EngineKit / apps/tool-call / add_calendar_event.json）
    eyebrow(s, "TOOL_CALL / 本地生成 · 真机截图", M, 3.72, GRAY, 5.6)
    s.shapes.add_picture(os.path.join(A, "vscode-toolcall.png"),
                         Inches(0.684), Inches(3.954), width=Inches(6.70))

    # 右：结果
    rx = Inches(7.65)
    eyebrow(s, "VERIFIED / 真机回归", rx, 4.02, BLUE, 4.8)
    txt(s, rx, Inches(4.28), Inches(4.9), Inches(0.24),
        [[("写入后回读，失败就报错。", 12.0, True, INK)]])
    proof = [("16/16", "场景 + 语音"), ("21.7s", "13 场景套件"), ("1804 MB", "峰值内存")]
    for i, (v, lab) in enumerate(proof):
        yy = 4.70 + i * 0.54
        txt(s, rx, Inches(yy), Inches(1.45), Inches(0.28),
            [[(v, 17, False, INK, EN)]])
        txt(s, rx + Inches(1.55), Inches(yy + 0.05), Inches(3.2), Inches(0.20),
            [[(lab, 7.4, False, GRAY, CN)]])
        if i < 2:
            rule(s, rx, Inches(yy + 0.40), Inches(4.8), LINE, 0.6)

    txt(s, M, Inches(6.62), Inches(11.8), Inches(0.28),
        [[("断网也能把事办成——这是云端助手给不了的体验。", 12.5, True, BLUE)]])
    source(s, "来源：EngineKit 真机流程 · 16/16 回归（13 场景 + 3 语音）· 2026-11-09 · PIPL：数据不出设备")


# ======================================================================
# P4 训练
# ======================================================================
def p4(prs):
    s = base(prs)
    kicker(s, "03 / TRAINING", 4)
    headline(s, ["训练到顶之后，", "我们把数学交给工具。"], y=0.82, size=29)
    lead(s, "1.7B 的数学容量有上限；继续堆数据没用，改用 CAS 做确定性计算。", 1.94, 11.4)

    eyebrow(s, "MATH / 69 QUESTIONS / OBJECTIVE", M, 2.34, GRAY)
    s.shapes.add_picture(os.path.join(A, "chart-training.png"),
                         M, Inches(2.52), width=Inches(7.15))
    txt(s, M, Inches(5.78), Inches(7.20), Inches(0.46),
        [[("SFT26 把 31 道真实 FRQ 训进 1.7B，仍是 47/69；\nSFT27e 改走 CAS 工具调用，+11 题。", 8.0, False, GRAY)]],
        ls=1.25, wrap=True)

    # 右侧深色结论
    px, py, pw, ph = Inches(8.15), Inches(2.30), Inches(4.43), Inches(3.72)
    panel_bg(s, "bg-ceiling.jpg", px, py, pw, ph)
    txt(s, px + Inches(0.28), py + Inches(0.26), Inches(3.9), Inches(0.18),
        [[("PURE TRAINING / CEILING", 6.8, True, RGBColor(0x8F, 0xA8, 0xC2), EN, False, 140)]])
    txt(s, px + Inches(0.28), py + Inches(0.56), Inches(3.9), Inches(0.85),
        [[("47/69", 54, False, WHITE, EN)]], ls=0.9)
    txt(s, px + Inches(0.28), py + Inches(1.34), Inches(3.8), Inches(0.20),
        [[("纯训练路线最高分", 8.0, True, ICE, CN)]])
    line(s, px + Inches(0.28), py + Inches(1.66), px + pw - Inches(0.28), py + Inches(1.66),
         RGBColor(0x2A, 0x44, 0x5C), 0.8)
    txt(s, px + Inches(0.28), py + Inches(1.84), Inches(3.85), Inches(0.64),
        [[("31 道真实 FRQ 也没有拉动 1.7B。", 15.5, True, WHITE)]], ls=1.2)
    txt(s, px + Inches(0.28), py + Inches(2.54), Inches(3.85), Inches(0.62),
        [[("不是数据质量，是容量。继续堆同类题会退化。", 8.2, False, RGBColor(0xB9, 0xC7, 0xD6))]],
        ls=1.3, wrap=True)
    txt(s, px + Inches(0.28), py + Inches(3.18), Inches(3.9), Inches(0.20),
        [[("CAS / 58/69", 11.0, True, BLUE, EN)]])

    stats = [("12.78M", "学术训练 tokens"), ("110", "SymPy 抓出错解"), ("31", "道真实 FRQ")]
    for i, (v, lab) in enumerate(stats):
        x = M + Inches(2.55) * i
        txt(s, x, Inches(6.38), Inches(2.3), Inches(0.24),
            [[(v, 15, False, INK, EN)]])
        txt(s, x + Inches(0.80), Inches(6.42), Inches(1.6), Inches(0.18),
            [[(lab, 7.2, False, GRAY, CN)]])
    source(s, "来源：SFT19 / SFT25 / SFT26 / SFT27e 评测 · train/lab-notebook/训练线总览（2026-11-09）")


# ======================================================================
# P5 引擎
# ======================================================================
def p5(prs):
    s = base(prs)
    kicker(s, "04 / ENGINE", 5)
    headline(s, ["同一套代码，", "0.6B / 1.7B 都装进 iPhone。"], y=0.82, size=29)
    lead(s, "EngineKit 全 Swift 封装 llama.cpp；模型、上下文、速度档都可换，代价写在界面上。", 1.94, 11.4)

    big_num(s, M, Inches(2.55), "61.1", "tok/s", size=96, color=INK, w=4.6)
    txt(s, M, Inches(4.12), Inches(4.0), Inches(0.22),
        [[("1.7B Q4_K_M · 18 Pro Max · 4K", 8.6, True, INK, CN)]])
    rule(s, M, Inches(4.42), Inches(3.95), LINE, 0.8)
    txt(s, M, Inches(4.62), Inches(4.0), Inches(0.40),
        [[("1.90", 27, False, INK, EN), (" GB", 9, True, GRAY, EN)]])
    txt(s, M, Inches(5.04), Inches(4.0), Inches(0.20),
        [[("峰值内存（4K 上下文）", 7.2, False, GRAY, CN)]])
    txt(s, M, Inches(5.36), Inches(4.0), Inches(0.20),
        [[("4K / 8K / 16K / 32K", 8.4, True, INK, MONO)]])
    txt(s, M, Inches(5.60), Inches(4.05), Inches(0.46),
        [[("KV 约 0.44 / 0.88 / 1.75 / 3.5 GB；\n8GB 机型建议 ≤8K。", 7.4, False, GRAY)]], ls=1.3)

    s.shapes.add_picture(os.path.join(A, "chart-engine.png"),
                         Inches(4.95), Inches(2.18), width=Inches(7.45))
    txt(s, Inches(5.10), Inches(6.40), Inches(7.2), Inches(0.20),
        [[("6 档量化实测 · 17/18 Pro Max 同协议 · 4 轮取后 3 轮 · 虚线为 2GB 预算", 7.0, False, GRAY, CN)]])

    txt(s, M, Inches(6.72), Inches(11.8), Inches(0.28),
        [[("向下兼容 0.6B，向上预留多 Agent 内存预算。", 12.0, True, BLUE)]])
    source(s, "来源：docs/评测/真机跑分对比-17ProMax-vs-18ProMax-20261103.md · 峰值内存单轮最高")


# ======================================================================
# P6 拍照做题
# ======================================================================
def p6(prs):
    s = base(prs)
    # 右侧深色面板
    panel_bg(s, "bg-math.jpg", Inches(7.65), 0, Inches(5.683), SH)
    kicker(s, "05 / MATH MODE", 6, color=BLUE, dark=True)
    txt(s, M, Inches(0.86), Inches(6.4), Inches(0.55),
        [[("PHOTO IN, PROOF OUT", 27, False, INK, EN)]])
    txt(s, M, Inches(1.62), Inches(6.5), Inches(0.36),
        [[("拍照做题：公式识别 → 本地 CAS → 可复核答案。", 15.5, True, INK)]])
    txt(s, M, Inches(2.08), Inches(6.2), Inches(0.22),
        [[("Texo 20M 公式识别 + math.js，全程在手机上。", 8.8, False, GRAY)]])

    txt(s, M, Inches(2.56), Inches(3.0), Inches(0.18),
        [[("INPUT / 题目图", 6.8, True, BLUE, EN, False, 140)]])
    s.shapes.add_picture(os.path.join(OLD, "formula-input-v5b.png"),
                         M + Inches(0.12), Inches(2.82), width=Inches(4.85))

    txt(s, M, Inches(5.38), Inches(2.5), Inches(0.18),
        [[("ANSWER / math.js", 6.8, True, BLUE, EN, False, 140)]])
    txt(s, M, Inches(5.58), Inches(2.2), Inches(0.95),
        [[("1", 74, False, BLUE, EN)]], ls=0.9)
    txt(s, M + Inches(1.15), Inches(6.10), Inches(4.0), Inches(0.22),
        [[("本机计算 · 无数值近似", 8.0, False, GRAY, CN)]])
    txt(s, M, Inches(6.56), Inches(5.9), Inches(0.24),
        [[("没有网络请求，也没有把题目发给云端。", 10.5, True, RUST)]])

    # 右侧：代码与指标
    rx = Inches(8.05)
    txt(s, rx, Inches(0.60), Inches(4.9), Inches(0.18),
        [[("OCR → PARSED → CAS", 7.0, True, RGBColor(0x8F, 0xA8, 0xC2), EN, False, 160)]])
    txt(s, rx, Inches(1.00), Inches(4.7), Inches(0.20),
        [[("OCR / LaTeX", 6.6, True, ICE, MONO)]])
    txt(s, rx, Inches(1.22), Inches(4.8), Inches(0.26),
        [[("\\lim_{x\\rarr0}\\frac{\\sin x}{x}", 9.6, False, WHITE, MONO)]])
    txt(s, rx, Inches(1.62), Inches(4.7), Inches(0.20),
        [[("题意 / PARSED", 6.6, True, ICE, MONO)]])
    txt(s, rx, Inches(1.84), Inches(4.75), Inches(0.44),
        [[("求 ((sin(x))/(x)) 在 x→0 时的极限。", 9.2, False, RGBColor(0xD8, 0xE4, 0xF0), MONO)]], wrap=True)
    line(s, rx, Inches(2.42), Inches(12.55), Inches(2.42), RGBColor(0x2A, 0x44, 0x5C), 0.8)

    stats = [("58/69", "数学端到端", "84.1% · SFT27e"),
             ("69/69", "工具发射", "schema 全通过"),
             ("186ms", "公式识别（热）", "18 Pro Max"),
             ("18/18", "Mac 对拍", "与 Python 逐字一致")]
    for i, (v, lab, note) in enumerate(stats):
        col, row = i % 2, i // 2
        x = rx + Inches(2.28) * col
        y = 2.66 + row * 1.16
        txt(s, x, Inches(y), Inches(2.12), Inches(0.42),
            [[(v, 22, False, WHITE, EN)]])
        txt(s, x, Inches(y + 0.44), Inches(2.12), Inches(0.20),
            [[(lab, 7.8, True, ICE, CN)]])
        txt(s, x, Inches(y + 0.66), Inches(2.12), Inches(0.20),
            [[(note, 6.6, False, RGBColor(0x8F, 0xA8, 0xC2), CN)]])

    line(s, rx, Inches(5.12), Inches(12.55), Inches(5.12), RGBColor(0x2A, 0x44, 0x5C), 0.8)
    txt(s, rx, Inches(5.30), Inches(4.5), Inches(0.60),
        [[("一张照片，三个本机步骤：\n识别公式 → 转成题意 → 调用 CAS。", 9.4, False, RGBColor(0xD8, 0xE4, 0xF0))]],
        ls=1.45)
    txt(s, rx, Inches(6.10), Inches(4.5), Inches(0.22),
        [[("Texo 20M · 77MB · ONNX Runtime 1.28", 7.0, False, RGBColor(0x8F, 0xA8, 0xC2), MONO)]])
    source(s, "来源：Texo 18 图对拍（2026-11-09）· SFT27e 69 题端到端 · iPhone 18 Pro Max 真机自检",
           x=M, w=6.6)


# ======================================================================
# P7 工具调用
# ======================================================================
def p7(prs):
    s = base(prs)
    kicker(s, "06 / TEST 01", 7)
    headline(s, ["40 道工具题，", "40/40 全部正确发射。"], y=0.82, size=29)
    lead(s, "命题书要求「用测试证明有没有用」——每次调用都落成 case 文件。", 1.94, 11.2)

    big_num(s, M, Inches(2.52), "40/40", size=92, color=INK, w=5.2)
    txt(s, M, Inches(4.08), Inches(5.0), Inches(0.22),
        [[("tool_call 正确发射 · 1.7B Q5/Q4", 9.2, True, INK)]])
    txt(s, M, Inches(4.36), Inches(4.9), Inches(0.34),
        [[("30 条训练分布 + 10 条泛化；schema 与 JSON 双 100%。", 7.6, False, GRAY)]], wrap=True)

    for i, (v, lab) in enumerate([("100%", "schema 校验"), ("100%", "JSON 解析")]):
        x = M + Inches(2.55) * i
        txt(s, x, Inches(4.92), Inches(2.45), Inches(0.34),
            [[(v, 22, False, BLUE if i == 0 else INK, EN)]])
        txt(s, x, Inches(5.30), Inches(2.40), Inches(0.20),
            [[(lab, 7.4, False, GRAY, CN)]])

    txt(s, M, Inches(5.78), Inches(4.8), Inches(0.18),
        [[("TOOLS / 白名单", 6.6, True, BLUE, EN, False, 140)]])
    txt(s, M, Inches(6.00), Inches(4.9), Inches(0.60),
        [[("add_calendar_event   add_reminder\ntranslate   summarize   clarify", 7.8, False, INK, MONO)]],
        ls=1.35)
    txt(s, M, Inches(6.56), Inches(4.9), Inches(0.20),
        [[("白名单外直接拒绝；写入前人工确认。", 7.0, False, GRAY, CN)]])

    # 右侧 40 格点阵
    rx, ry = 7.55, 2.34
    eyebrow(s, "40 CASES / 30 TRAIN + 10 HELDOUT", Inches(rx), Inches(ry), BLUE, 5.0)
    cell, gap = 0.44, 0.22
    for i in range(40):
        col, row = i % 8, i // 8
        color = BLUE if i < 30 else MINT
        rect(s, Inches(rx + col * (cell + gap)), Inches(ry + 0.32 + row * (cell + gap)),
             Inches(cell), Inches(cell), color)
    # 图例
    rect(s, Inches(rx), Inches(5.90), Inches(0.10), Inches(0.10), BLUE)
    txt(s, Inches(rx + 0.16), Inches(5.86), Inches(1.8), Inches(0.18),
        [[("30 训练分布", 6.8, False, GRAY, CN)]])
    rect(s, Inches(rx + 1.75), Inches(5.90), Inches(0.10), Inches(0.10), MINT)
    txt(s, Inches(rx + 1.91), Inches(5.86), Inches(1.6), Inches(0.18),
        [[("10 泛化", 6.8, False, GRAY, CN)]])

    line(s, Inches(rx), Inches(6.14), Inches(12.58), Inches(6.14), LINE, 0.6)
    txt(s, Inches(rx), Inches(6.24), Inches(4.95), Inches(0.44),
        [[("不是「感觉能用」，是逐题可复核；\n失败样例也保留，能回放。", 8.0, False, GRAY)]], ls=1.3)
    txt(s, Inches(rx), Inches(6.66), Inches(4.95), Inches(0.22),
        [[("40/40 不是全场景全对，是这套 40 题全对。", 8.4, True, RUST)]])
    source(s, "来源：SFT19 评测（40 题，temp 0.7）· SFT3 工具遵循率专项 · 16/16 真机回归")


# ======================================================================
# P8 日期
# ======================================================================
def p8(prs):
    s = base(prs)
    kicker(s, "07 / TEST 02", 8)
    headline(s, ["日期题，", "从 15/15 全错到 58/60。"], y=0.82, size=29)
    lead(s, "改前 15 题全错；补日期表后把验收集扩到 60 题，再训边界。", 1.94, 11.2)

    big_num(s, M, Inches(2.52), "58/60", size=92, color=INK, w=5.2)
    txt(s, M, Inches(4.06), Inches(5.0), Inches(0.22),
        [[("日期题精确匹配 · SFT20d", 9.2, True, INK)]])
    txt(s, M, Inches(4.34), Inches(5.0), Inches(0.22),
        [[("上一版 93.3%；这一版 96.7%。", 7.6, False, GRAY, CN)]])

    rows = [("96.7%", "60 题日期集"), ("16/16", "边界题"), ("8/8", "工人四工种")]
    for i, (v, lab) in enumerate(rows):
        y = 4.82 + i * 0.46
        txt(s, M, Inches(y), Inches(1.45), Inches(0.28),
            [[(v, 18, False, BLUE if i == 0 else INK, EN)]])
        txt(s, M + Inches(1.55), Inches(y + 0.04), Inches(3.4), Inches(0.20),
            [[(lab, 7.4, False, GRAY, CN)]])
        if i < 2:
            rule(s, M, Inches(y + 0.36), Inches(4.7), LINE, 0.6)

    s.shapes.add_picture(os.path.join(A, "chart-dates.png"),
                         Inches(6.55), Inches(2.18), width=Inches(5.95))
    txt(s, Inches(6.70), Inches(5.12), Inches(5.7), Inches(0.20),
        [[("SFT20b → SFT20c → SFT20d / 60 题日期集", 7.0, False, GRAY, MONO)]])

    txt(s, Inches(6.70), Inches(5.50), Inches(5.7), Inches(0.18),
        [[("STILL WRONG / 写进限制", 6.8, True, RUST, EN, False, 140)]])
    txt(s, Inches(6.70), Inches(5.74), Inches(5.7), Inches(0.52),
        [[("2027-02-29 不存在 → 应滚到 2028；\n23:30 + 3h 跨天 → 只加了 1h。", 8.4, False, INK, CN)]],
        ls=1.35)
    txt(s, M, Inches(6.58), Inches(11.8), Inches(0.28),
        [[("剩下的 2 题写进限制，不假装 100%。", 12.5, True, RUST)]])
    source(s, "来源：SFT20b / SFT20c / SFT20d 日期评测（60 题，2026-11-08）· 训练线总览")


# ======================================================================
# P9 风险
# ======================================================================
def p9(prs):
    s = base(prs)
    kicker(s, "08 / RISK & HUMAN", 9)
    headline(s, ["AI 判断错了，", "产品怎么办？"], y=0.82, size=29)
    lead(s, "命题书完成重点：怎样提醒使用者、由谁确认和处理。", 1.94, 11.2)

    gates = [
        ("01", "MODEL", "幻觉 / 编造工具", "白名单 + 「不确定」标注", False),
        ("02", "SCHEMA", "参数错 / 时间格式", "必填 + 正则，拒绝执行", False),
        ("03", "HUMAN", "时间 / 地点写错", "系统确认框，显示可读日期", True),
        ("04", "WRITE", "写入失败", "回读校验，如实报错", False),
    ]
    # 全幅深色「四道闸门」带：唯一一处整幅深色分区，压住风险页的重心
    panel_bg(s, "bg-gates.jpg", 0, Inches(2.62), SW, Inches(2.10))
    txt(s, M, Inches(2.82), Inches(6.0), Inches(0.18),
        [[("DEFENSE IN DEPTH / 四道闸门", 6.8, True, RGBColor(0x8F, 0xA8, 0xC2), EN, False, 160)]])
    line(s, M, Inches(3.30), Inches(12.58), Inches(3.30), RGBColor(0x2A, 0x44, 0x5C), 0.8)
    for i, (num, name, risk, how, hot) in enumerate(gates):
        x = M + Inches(3.02) * i
        ring = RGBColor(0x4F, 0x6B, 0x85)
        circle_outline(s, x, Inches(3.12), Inches(0.36), BLUE if hot else ring,
                       2.2 if hot else 1.0, fill=NAVY)
        if hot:
            dot = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.13), Inches(3.25),
                                     Inches(0.10), Inches(0.10))
            dot.fill.solid(); dot.fill.fore_color.rgb = BLUE
            dot.line.fill.background(); dot.shadow.inherit = False
        txt(s, x, Inches(3.60), Inches(2.8), Inches(0.18),
            [[(num, 7.0, True, BLUE if hot else RGBColor(0x8F, 0xA8, 0xC2), MONO)]])
        txt(s, x, Inches(3.80), Inches(2.8), Inches(0.24),
            [[(name, 11.0, True, BLUE if hot else WHITE, EN, False, 120)]])
        txt(s, x, Inches(4.12), Inches(2.7), Inches(0.22),
            [[(risk, 8.8, True, WHITE, CN)]])
        txt(s, x, Inches(4.36), Inches(2.65), Inches(0.30),
            [[(how, 7.4, False, RGBColor(0xB9, 0xC7, 0xD6), CN)]], ls=1.2, wrap=True)

    rect(s, M, Inches(5.02), Inches(0.06), Inches(0.62), BLUE)
    txt(s, M + Inches(0.20), Inches(4.96), Inches(11.6), Inches(0.34),
        [[("红线：AI 只提供建议与结构化结果，最终决定权永远在人。", 18, True, INK)]])
    txt(s, M + Inches(0.20), Inches(5.38), Inches(11.6), Inches(0.22),
        [[("写入前弹系统确认框；用户点「允许」才执行。", 8.4, False, GRAY, CN)]])

    rule(s, M, Inches(5.86), Inches(11.83), LINE, 0.8)
    txt(s, M, Inches(6.02), Inches(5.6), Inches(0.18),
        [[("APP STORE / 合规", 6.6, True, BLUE, EN, False, 140)]])
    txt(s, M, Inches(6.22), Inches(5.6), Inches(0.60),
        [[("不下载可执行代码 · 模型仅本地推理\n权限最小化 · 隐私政策 · 无账号与统计 SDK", 7.2, False, GRAY)]],
        ls=1.35)
    txt(s, Inches(7.05), Inches(6.02), Inches(5.5), Inches(0.18),
        [[("CURRENT LIMITS / 诚实披露", 6.6, True, RUST, EN, False, 140)]])
    txt(s, Inches(7.05), Inches(6.22), Inches(5.5), Inches(0.60),
        [[("1.7B 复杂推理有限 · 工具只覆盖日历/提醒/翻译/摘要\nAndroid 未覆盖 · 日期 2/60 错 · 数学 11/69 错",
           7.2, False, GRAY)]], ls=1.35)
    source(s, "来源：ToolKit 白名单 / schema · 16/16 真机回归 · 日期 60 题 · App Store Review Guidelines 2.5.2 / 5.1.1")


# ======================================================================
# P10 团队与路线
# ======================================================================
def p10(prs):
    s = base(prs)
    kicker(s, "09 / TEAM & NEXT", 10, dark=True)
    headline(s, ["三个人，三个智能体，", "一条评审链。"], y=0.82, size=29)
    lead(s, "队长把产品做出来，队员证明它能跑、别人用得起来；每个产出都经 PR 评审后合并。", 1.96, 6.5)

    # ---------- 分工表 ----------
    eyebrow(s, "TEAM / 分工", M, 2.50, BLUE)
    head_y = 2.72
    cols = [M, M + Inches(1.62), M + Inches(4.06)]
    for x, w, h in zip(cols, [Inches(1.55), Inches(2.36), Inches(2.62)],
                       ["姓名 / 角色", "智能体承担", "人承担"]):
        txt(s, x, Inches(head_y), w, Inches(0.16), [[(h, 6.2, True, LIGHT, CN)]])
    rule(s, M, Inches(head_y + 0.19), Inches(6.68), LINE, 0.7)

    team = [("樊一凡", "队长 · 架构 / 训练 / 发布",
             "代码骨架 · 调试 · 批量数据处理", "架构决策 · 评审与合并"),
            ("张曜阳", "队员 · 首次安装体验",
             "整理卡点记录 · 汇总共性问题", "首装走查 · 记录卡点"),
            ("薛亦湘", "队员 · 用户验证与演示",
             "整理访谈记录 · 起草分镜脚本", "组织同学试用 · 逐条核对数字")]
    for i, (name, role, agent, human) in enumerate(team):
        y = head_y + 0.26 + i * 0.48
        txt(s, cols[0], Inches(y), Inches(1.55), Inches(0.18),
            [[(name, 9.2, True, INK)]])
        txt(s, cols[0], Inches(y + 0.19), Inches(1.55), Inches(0.16),
            [[(role, 6.4, False, GRAY)]])
        txt(s, cols[1], Inches(y + 0.01), Inches(2.36), Inches(0.34),
            [[(agent, 7.4, False, INK)]], ls=1.15, wrap=True)
        txt(s, cols[2], Inches(y + 0.01), Inches(2.62), Inches(0.34),
            [[(human, 7.4, True, INK)]], ls=1.15, wrap=True)
        if i < 2:
            rule(s, M, Inches(y + 0.42), Inches(6.68), LINE, 0.5)

    # ---------- 流水线 ----------
    eyebrow(s, "WORKFLOW / 一件任务的全过程", M, 4.44, BLUE)
    py, ph = 4.64, 0.70
    rect(s, M, Inches(py), Inches(6.68), Inches(ph), fill=None, line=LINE, line_w=0.7)
    steps = [("01", "Issue 任务单", "目标 · 验收 · 证据"),
             ("02", "独立分支", "一人一支"),
             ("03", "提交 PR", "附截图与原话"),
             ("04", "队长评审", "打回或批准"),
             ("05", "合并 main", "编号进记录")]
    cw = 6.68 / 5
    for i, (num, title, desc) in enumerate(steps):
        cx = M + Inches(cw * i)
        if i:
            line(s, cx, Inches(py), cx, Inches(py + ph), LINE, 0.5)
        txt(s, cx + Inches(0.10), Inches(py + 0.07), Inches(cw - 0.16), Inches(0.13),
            [[(num, 6.0, True, BLUE, MONO)]])
        txt(s, cx + Inches(0.10), Inches(py + 0.21), Inches(cw - 0.16), Inches(0.18),
            [[(title, 8.2, True, INK)]])
        txt(s, cx + Inches(0.10), Inches(py + 0.42), Inches(cw - 0.16), Inches(0.15),
            [[(desc, 6.3, False, GRAY)]])

    # ---------- 工程纪律 ----------
    eyebrow(s, "DISCIPLINE / 工程纪律", M, 5.50, BLUE)
    sep = [("  /  ", 7.2, False, LIGHT)]
    txt(s, M, Inches(5.70), Inches(6.68), Inches(0.18),
        [[("计划先行", 7.2, True, INK)] + sep
         + [("门禁全绿", 7.2, True, INK)] + sep
         + [("16 项真机回归", 7.2, True, INK)] + sep
         + [("评测结果落盘", 7.2, True, INK)] + sep
         + [("第三方许可逐项标注", 7.2, True, INK)]])
    txt(s, M, Inches(5.92), Inches(6.68), Inches(0.16),
        [[("训练数据：云端大模型 + SymPy 后验　·　真题转化与开发：AI 协作 + 人工复核", 6.6, False, GRAY)]])

    # ---------- 路线 ----------
    eyebrow(s, "ROADMAP / 已实现 · 进行中 · 规划", M, 6.24, BLUE)
    line(s, M, Inches(6.56), M + Inches(6.68), Inches(6.56), LINE, 1.0)
    roadmap = [("01", "CAS"), ("02", "4B"), ("03", "TestFlight"), ("04", "Multi-Agent"), ("05", "Android")]
    for i, (num, name) in enumerate(roadmap):
        x = M + Inches(1.34) * i
        hot = num == "04"
        rect(s, x, Inches(6.52), Inches(0.09), Inches(0.09), RUST if hot else BLUE)
        txt(s, x, Inches(6.68), Inches(1.28), Inches(0.14),
            [[(num, 6.2, True, RUST if hot else GRAY, MONO)]])
        txt(s, x, Inches(6.84), Inches(1.28), Inches(0.16),
            [[(name, 7.2, True, INK, EN)]])

    # ---------- 右：深色收尾 ----------
    panel_bg(s, "bg-closing.jpg", Inches(7.65), 0, Inches(5.683), SH)
    txt(s, Inches(8.05), Inches(0.60), Inches(4.7), Inches(0.18),
        [[("CLOSING", 7.0, True, RGBColor(0x8F, 0xA8, 0xC2), EN, False, 180)]])
    txt(s, Inches(8.05), Inches(1.10), Inches(4.6), Inches(2.0),
        [[("把 AI 从云端\n搬进口袋，\n把编排权交给学生。", 31, True, WHITE)]], ls=1.22)
    line(s, Inches(8.05), Inches(3.62), Inches(12.25), Inches(3.62), RGBColor(0x2A, 0x44, 0x5C), 0.8)
    txt(s, Inches(8.05), Inches(3.86), Inches(4.5), Inches(0.22),
        [[("GitHub", 7.0, True, RGBColor(0x8F, 0xA8, 0xC2), EN)]])
    txt(s, Inches(8.05), Inches(4.08), Inches(4.5), Inches(0.24),
        [[("github.com/fanyifan090409-dev/mobile-llm-engine", 7.4, False, ICE, MONO)]])
    txt(s, Inches(8.05), Inches(4.52), Inches(4.5), Inches(0.22),
        [[("提交物 / 10 页 PPT + ≤8 分钟真机 Demo", 8.2, False, RGBColor(0xD8, 0xE4, 0xF0), CN)]])
    txt(s, Inches(8.05), Inches(6.55), Inches(4.5), Inches(0.20),
        [[("2026 / AIY HACK LEAGUE", 7.0, True, RGBColor(0x8F, 0xA8, 0xC2), EN, False, 160)]])

    source(s, "来源：项目仓库 · 训练/评测日志 · 第三方许可证（MIT / Apache 2.0 / AGPL-3.0）")


def main():
    prs = Presentation()
    prs.slide_width = SW
    prs.slide_height = SH
    prs.core_properties.title = "Pocket Intelligence — 口袋里的 Agent 实验室"
    prs.core_properties.author = "樊一凡"
    prs.core_properties.subject = "AIY 27 高中组 PRO · 题目一 AI×科学工程（自定方向）"
    p1(prs); p2(prs); p3(prs); p4(prs); p5(prs)
    p6(prs); p7(prs); p8(prs); p9(prs); p10(prs)
    prs.save(OUT)
    print("saved", OUT, "slides", len(prs.slides))


if __name__ == "__main__":
    main()
