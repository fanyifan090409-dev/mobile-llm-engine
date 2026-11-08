#!/usr/bin/env python3
"""AIY 27 PPT 生成 v3（10 页高密度重构版）。

v3 变更（2026-11-03 用户要求）：
- 全篇叙事重构：数据不出域/离线安全 → 美高课程特训 → 日历等日常工具 → 本地部署
- 每页提高信息密度：标题 + 一句话结论 + 2~3 栏证据/数据，不再整页只放一张图
- 图表换成不带图内标题的 C1-C4 半页图；引擎/训练链/风险页用 PPTX 原生形状，WPS 可编辑
- 固定网格：标题 0.30in / 副标题 0.82in / 内容 1.38-6.30in / 结论条 6.42in / 页脚 7.08in
用法：.venv/bin/python docs/aiy27/figures/gen_pptx.py
验证：Keynote 打开导出 PDF → scripts/pdf2png.swift → 逐页目检
"""
import os
import struct

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "AIY27-PPT.pptx")

DARK = RGBColor(0x1D, 0x1D, 0x1F)
MID = RGBColor(0x6E, 0x6E, 0x73)
LIGHT = RGBColor(0xAE, 0xAE, 0xB2)
BLUE = RGBColor(0x0A, 0x84, 0xFF)
BLUE_D = RGBColor(0x00, 0x5F, 0xC7)
GREEN = RGBColor(0x30, 0xD1, 0x58)
GREEN_D = RGBColor(0x1B, 0x8F, 0x3A)
ORANGE = RGBColor(0xFF, 0x9F, 0x0A)
ORANGE_D = RGBColor(0xB2, 0x5F, 0x00)
RED = RGBColor(0xFF, 0x3B, 0x30)
HAIR = RGBColor(0xD9, 0xD9, 0xDE)
CARD = RGBColor(0xF5, 0xF5, 0xF7)
BLUECARD = RGBColor(0xEA, 0xF3, 0xFF)
GREEN_CARD = RGBColor(0xEC, 0xFA, 0xEF)
ORANGE_CARD = RGBColor(0xFF, 0xF5, 0xE6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "PingFang SC"

SW, SH = Inches(13.333), Inches(7.5)
M = Inches(0.55)
CONTENT_W = SW - 2 * M
TITLE_Y = Inches(0.30)
SUB_Y = Inches(0.82)
HAIR_Y = Inches(1.22)
CONC_Y = Inches(6.42)
FOOT_Y = Inches(7.08)


def png_size(path):
    with open(path, "rb") as f:
        d = f.read(26)
    w, h = struct.unpack(">II", d[16:24])
    return w, h


def set_font(run, size, bold=False, color=DARK, name=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {})
            rPr.append(e)
        e.set("typeface", name)


def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def rect(slide, x, y, w, h, fill=CARD, line=None, line_w=0.75, round_=True, radius=0.10):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE, x, y, w, h)
    if round_:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    return shp


def textbox(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.TOP, space_after=4, line_spacing=1.0):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.line_spacing = line_spacing
        runs = para if isinstance(para, list) else [para]
        for (t, s, b, c) in runs:
            r = p.add_run()
            r.text = t
            set_font(r, s, b, c)
    return tb


def title_block(slide, title, sub=None):
    textbox(slide, M, TITLE_Y, CONTENT_W, Inches(0.52),
            [[(title, 25, True, DARK)]], space_after=0)
    if sub:
        textbox(slide, M, SUB_Y, CONTENT_W, Inches(0.34),
                [[(sub, 11.5, False, MID)]], space_after=0)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, M, HAIR_Y, CONTENT_W, Pt(1))
    line.fill.solid()
    line.fill.fore_color.rgb = HAIR
    line.line.fill.background()
    line.shadow.inherit = False


def footer(slide, page, source=None):
    if source:
        textbox(slide, M, FOOT_Y, Inches(11.1), Inches(0.25),
                [[(source, 8, False, LIGHT)]], space_after=0)
    textbox(slide, SW - M - Inches(0.8), FOOT_Y, Inches(0.8), Inches(0.25),
            [[(f"{page:02d}", 8.5, False, LIGHT)]], align=PP_ALIGN.RIGHT, space_after=0)


def conclusion(slide, text):
    rect(slide, M, CONC_Y, CONTENT_W, Inches(0.42), fill=BLUECARD, line=None)
    textbox(slide, M + Inches(0.18), CONC_Y + Inches(0.08), CONTENT_W - Inches(0.36),
            Inches(0.28), [[(text, 12.5, True, BLUE_D)]], space_after=0)


def fit_image(slide, path, x, y, w, h, top_align=False):
    iw, ih = png_size(path)
    scale = min(w / iw, h / ih)
    pw, ph = int(iw * scale), int(ih * scale)
    px = x + (w - pw) // 2
    py = y if top_align else y + (h - ph) // 2
    return slide.shapes.add_picture(path, px, py, width=pw, height=ph)


def fig(name):
    return os.path.join(HERE, name)


def pill(slide, x, y, w, h, text, color=BLUE, fill=BLUECARD, size=9, bold=True):
    rect(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    textbox(slide, x, y + (h - Inches(0.18)) / 2, w, Inches(0.18),
            [[(text, size, bold, color)]], align=PP_ALIGN.CENTER, space_after=0)


def metric(slide, x, y, w, h, value, label, color=BLUE, note=None, value_size=19):
    rect(slide, x, y, w, h, fill=WHITE, line=HAIR, line_w=0.75)
    lines = [[(value, value_size, True, color)]]
    lines.append([(label, 9, False, MID)])
    if note:
        lines.append([(note, 8, False, LIGHT)])
    textbox(slide, x + Inches(0.15), y + Inches(0.09), w - Inches(0.30), h - Inches(0.14),
            lines, space_after=1)


def section_label(slide, x, y, w, text, color=MID):
    textbox(slide, x, y, w, Inches(0.25), [[(text, 9.5, True, color)]], space_after=0)


def flow_box(slide, x, y, w, h, title, detail, color=BLUE, fill=CARD,
             num=None, title_size=11.5, detail_size=9.0):
    rect(slide, x, y, w, h, fill=fill, line=None)
    tx = x + Inches(0.13)
    tw = w - Inches(0.26)
    if num is not None:
        rect(slide, x + Inches(0.13), y + Inches(0.13), Inches(0.28), Inches(0.28),
             fill=color, line=None, radius=0.5)
        textbox(slide, x + Inches(0.13), y + Inches(0.16), Inches(0.28), Inches(0.22),
                [[(str(num), 9, True, WHITE)]], align=PP_ALIGN.CENTER, space_after=0)
        tx = x + Inches(0.50)
        tw = w - Inches(0.62)
    textbox(slide, tx, y + Inches(0.10), tw, h - Inches(0.16),
            [[(title, title_size, True, DARK)],
             [(detail, detail_size, False, MID)]], space_after=1)


def arrow_down(slide, x, y, w=Inches(0.16), h=Inches(0.14), color=LIGHT):
    shp = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False


def table(slide, x, y, widths, rows, row_h, header=True,
          size=9.2, header_size=8.8, aligns=None):
    total_w = sum(widths, Inches(0))
    ry = y
    for ri, row in enumerate(rows):
        is_head = header and ri == 0
        if is_head:
            rect(slide, x, ry, total_w, row_h, fill=RGBColor(0xEC, 0xEC, 0xF0), round_=False)
        elif ri % 2 == 0:
            rect(slide, x, ry, total_w, row_h, fill=CARD, round_=False)
        cx = x
        for ci, cell in enumerate(row):
            if isinstance(cell, str):
                runs = [(cell, header_size if is_head else size,
                         is_head, MID if is_head else DARK)]
            else:
                runs = cell
            al = PP_ALIGN.LEFT
            if aligns and aligns[ci] == "center":
                al = PP_ALIGN.CENTER
            textbox(slide, cx + Inches(0.07), ry, widths[ci] - Inches(0.10), row_h,
                    [runs], align=al, anchor=MSO_ANCHOR.MIDDLE, space_after=0)
            cx += widths[ci]
        ry += row_h
    return ry


# ====================================================================== 页面

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH

# ---------------- S1 封面
s = new_slide(prs)
rect(s, 0, 0, SW, SH, fill=WHITE)
rect(s, M, Inches(1.18), Inches(0.52), Inches(0.08), fill=BLUE, round_=False)
textbox(s, M, Inches(1.36), Inches(8.8), Inches(0.3),
        [[("AIY 27 初级站 · 高中组 Pro 组 · 题目一 AI×科学工程（自定方向）", 13, True, BLUE)]])
textbox(s, M, Inches(1.78), Inches(9.0), Inches(0.95),
        [[("把 AI 装进口袋", 50, True, DARK)]], space_after=0)
textbox(s, M, Inches(2.72), Inches(9.0), Inches(0.62),
        [[("数据不出域的本地 AI 助手", 31, True, BLUE_D)]], space_after=0)
textbox(s, M, Inches(3.45), Inches(8.8), Inches(0.4),
        [[("为美高课程特训 · 离线可用 · 一句话完成日历/提醒等日常任务", 16, False, DARK)]])
textbox(s, M, Inches(3.92), Inches(8.9), Inches(0.55),
        [[("国际学校网络受限、出国流量贵、成绩单与日程不想上云——这些场景不该被 AI 排除在外。", 11.5, False, MID)]])

mx = M
mw = Inches(2.18)
for value, label, color in [
        ("61.1 tok/s", "18 Pro Max · 1.7B 本地推理", BLUE),
        ("0 上传", "推理全程本机 · 飞行可用", GREEN_D),
        ("90–100%", "工具调用 schema 通过率", ORANGE),
        ("12/12", "真机回归用例通过", BLUE_D)]:
    metric(s, mx, Inches(4.62), mw, Inches(1.02), value, label, color, value_size=17)
    mx += mw + Inches(0.16)

textbox(s, M, Inches(6.02), Inches(9.0), Inches(0.5),
        [[("团队：＿＿＿＿＿＿＿＿＿＿　　演示人：＿＿＿＿＿＿＿＿＿＿　　GitHub：mobile-llm-engine", 11, False, MID)]])
textbox(s, M, Inches(6.52), Inches(9.6), Inches(0.4),
        [[("模型口径：基于 Qwen3 开源模型继续训练 · 推理底座 llama.cpp（MIT）· 评测数字来自本机训练与真机日志", 9, False, LIGHT)]])

# 右侧手机示意（原生形状，正式版可换真机截图）
px, py, pw, ph = Inches(9.85), Inches(1.25), Inches(2.95), Inches(5.35)
rect(s, px, py, pw, ph, fill=WHITE, line=HAIR, line_w=1.0, radius=0.14)
rect(s, px + Inches(0.12), py + Inches(0.42), pw - Inches(0.24), ph - Inches(0.72),
     fill=RGBColor(0xF2, 0xF6, 0xFD), line=None, radius=0.10)
rect(s, px + pw / 2 - Inches(0.45), py + Inches(0.16), Inches(0.9), Inches(0.14),
     fill=RGBColor(0xE5, 0xE5, 0xEA), line=None, radius=0.5)
pill(s, px + Inches(0.22), py + Inches(0.62), pw - Inches(0.44), Inches(0.28),
     "● 离线 · 数据不出设备", GREEN_D, GREEN_CARD, size=7.5)
rect(s, px + Inches(0.22), py + Inches(1.10), Inches(2.1), Inches(0.62),
     fill=WHITE, line=HAIR, line_w=0.6, radius=0.18)
textbox(s, px + Inches(0.34), py + Inches(1.20), Inches(1.9), Inches(0.45),
        [[("家长会，明天下午三点，学校", 8.2, False, DARK)]], space_after=0)
rect(s, px + Inches(0.48), py + Inches(1.90), Inches(2.25), Inches(1.28),
     fill=BLUECARD, line=None, radius=0.14)
textbox(s, px + Inches(0.62), py + Inches(2.02), Inches(2.0), Inches(1.05),
        [[("本地 1.7B 推理", 9, True, BLUE_D)],
         [("add_calendar_event", 8.5, True, DARK)],
         [("2026-11-04 15:00 · 学校", 8, False, MID)]], space_after=2)
rect(s, px + Inches(0.30), py + Inches(3.38), Inches(2.45), Inches(0.86),
     fill=GREEN_CARD, line=None, radius=0.14)
textbox(s, px + Inches(0.44), py + Inches(3.49), Inches(2.2), Inches(0.65),
        [[("✓ 已写入系统日历", 9, True, GREEN_D)],
         [("用户确认后才执行", 8, False, MID)]], space_after=2)
textbox(s, px + Inches(0.30), py + Inches(4.55), Inches(2.4), Inches(0.3),
        [[("Q4_K_M · 4K · 0 上传", 8.5, False, MID)]], space_after=0)

# ---------------- S2 命题理解与目标用户
s = new_slide(prs)
title_block(s, "命题理解 · 想用 AI 的人，被两件事挡住", "没有网，或者不敢把数据交出去——国际学校学生每天都在经历")
rect(s, M, Inches(1.42), CONTENT_W, Inches(0.78), fill=BLUECARD, line=None)
textbox(s, M + Inches(0.22), Inches(1.55), CONTENT_W - Inches(0.44), Inches(0.52),
        [[("问题一句话：", 14, True, BLUE),
          ("手机 AI 助手依赖云端——断网即失效，数据出设备；想随时随地用 AI 的人，两头都为难。", 14, True, DARK)]],
        space_after=0)
textbox(s, M, Inches(2.32), Inches(1.55), Inches(0.3),
        [[("目标用户", 12, True, BLUE)]], space_after=0)
textbox(s, M + Inches(1.45), Inches(2.30), CONTENT_W - Inches(1.45), Inches(0.62),
        [[("国际学校 / 美高在读学生（我们就是用户）：教室与宿舍网不稳、出国流量贵、成绩单/日程/健康记录不愿上云。", 10.8, True, DARK)],
         [("核心需求：离线可用 · 数据不出设备 · 懂美高课程 · 能替我把事办成（日历/提醒）。", 10.2, False, MID)]],
        space_after=2)
textbox(s, M, Inches(3.10), Inches(8.0), Inches(0.3),
        [[("为什么「不敢交出去」——2026 年公开报道的真实事故", 12.5, True, DARK)]], space_after=0)
textbox(s, M + Inches(8.2), Inches(3.12), CONTENT_W - Inches(8.2), Inches(0.3),
        [[("共同点：数据一旦离开设备，控制权就没了", 9.5, True, RED)]], align=PP_ALIGN.RIGHT, space_after=0)

widths = [Inches(1.0), Inches(5.55), Inches(2.6), Inches(3.08)]
rows = [
    ["时间", "事件", "泄漏内容", "来源"],
    ["2026.04–06", [("Claude Code 安全后门", 9.2, True, DARK), ("：未经同意回传地域、身份标识等敏感数据", 8.7, False, DARK)],
     "用户敏感信息", "求是网 / 工信部风险提示"],
    ["2026.09", [("智谱 ZCode 传包风波", 9.2, True, DARK), ("：整个项目连同修改历史打包加密上传云端", 8.7, False, DARK)],
     [("3.29 万文件 / 4.11 亿明文字符", 8.8, True, ORANGE)], "36氪 / 掘金（企业函件称）"],
    ["2026.08", [("PROMPTPEEK 攻击", 9.2, True, DARK), ("：共享缓存侧信道可还原其他用户提问", 8.7, False, DARK)],
     "用户提问内容", "NDSS 2025 论文"],
    ["2026.08", [("Reasoning Trace Theft", 9.2, True, DARK), ("：三家 API 加密推理链缺陷，跨模型重放窃取思维链", 8.7, False, DARK)],
     "思维链 / 推理内容", "CSA 研究 / 绿盟分析"],
    ["2026 上半年", [("法国医院病历事件", 9.2, True, DARK), ("：医生用 Claude 3 写病历，8 个月 1247 份", 8.7, False, DARK)],
     "患者医疗数据", "法媒隐私审计报告"],
]
table(s, M, Inches(3.42), widths, rows, Inches(0.47), header=True)
footer(s, 2, "来源：2026 年公开报道（求是网 / 工信部 NVDB、36氪 / 掘金、NDSS 2025、CSA / 绿盟、法媒审计）· 用户调研")
conclusion(s, "当 AI 出错或泄密的代价由用户承担时，最稳的解法是让数据根本不离开设备。")

# ---------------- S3 当前流程 vs AI 机会
s = new_slide(prs)
title_block(s, "当前流程 vs AI 机会 · 云端 AI 的两个硬伤，正是本地方案的入口",
            "同样一句「帮我加个日程」，云端要把数据送出去，本地不用")
rect(s, M, Inches(1.42), Inches(5.9), Inches(4.55), fill=CARD, line=None)
textbox(s, M + Inches(0.25), Inches(1.55), Inches(5.4), Inches(0.3),
        [[("现在的云端助手", 14, True, MID)]], space_after=0)
lx, lw = M + Inches(0.25), Inches(5.4)
cloud = [
    ("输入一句话", "「家长会，明天下午三点，学校」"),
    ("上传到云端", "请求离开设备，进入第三方服务器"),
    ("云端大模型推理", "依赖网络、账号、额度与厂商策略"),
    ("返回结果", "断网 = 不可用；数据已经出设备"),
]
yy = Inches(2.00)
for i, (t, d) in enumerate(cloud, 1):
    flow_box(s, lx, yy, lw, Inches(0.58), t, d, color=MID, num=i, title_size=11, detail_size=8.8)
    if i < 4:
        arrow_down(s, lx + lw / 2 - Inches(0.08), yy + Inches(0.59))
    yy += Inches(0.73)
pill(s, lx, Inches(5.52), Inches(1.55), Inches(0.30), "断网即失效", RED, RGBColor(0xFF, 0xEB, 0xEA), size=8)
pill(s, lx + Inches(1.65), Inches(5.52), Inches(1.55), Inches(0.30), "数据出设备", ORANGE_D, ORANGE_CARD, size=8)
pill(s, lx + Inches(3.30), Inches(5.52), Inches(1.70), Inches(0.30), "模型不是你的", MID, RGBColor(0xEC, 0xEC, 0xF0), size=8)

vs = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(6.55), Inches(3.40), Inches(0.62), Inches(0.62))
vs.fill.solid(); vs.fill.fore_color.rgb = DARK; vs.line.fill.background(); vs.shadow.inherit = False
textbox(s, Inches(6.55), Inches(3.58), Inches(0.62), Inches(0.25),
        [[("VS", 10, True, WHITE)]], align=PP_ALIGN.CENTER, space_after=0)

rect(s, Inches(7.23), Inches(1.42), Inches(5.55), Inches(4.55), fill=BLUECARD, line=None)
textbox(s, Inches(7.48), Inches(1.55), Inches(5.1), Inches(0.3),
        [[("我们的本地助手（iOS 真机）", 14, True, BLUE_D)]], space_after=0)
local = [
    ("输入一句话", "同样的任务，不需要联网"),
    ("本地 1.7B 推理", "权重在手机里，数据不出设备"),
    ("结构化工具调用", "add_calendar_event + 参数"),
    ("系统确认", "用户点「允许」才执行"),
    ("写入日历", "结果卡 + 本地日志，可复核"),
]
rx, rw = Inches(7.48), Inches(5.05)
yy = Inches(1.98)
for i, (t, d) in enumerate(local, 1):
    flow_box(s, rx, yy, rw, Inches(0.56), t, d, color=BLUE, fill=WHITE, num=i, title_size=10.8, detail_size=8.6)
    if i < 5:
        arrow_down(s, rx + rw / 2 - Inches(0.08), yy + Inches(0.57), color=RGBColor(0x9C, 0xCB, 0xFF))
    yy += Inches(0.69)
pill(s, rx, Inches(5.52), Inches(1.55), Inches(0.30), "飞行模式可用", GREEN_D, GREEN_CARD, size=8)
pill(s, rx + Inches(1.65), Inches(5.52), Inches(1.55), Inches(0.30), "0 上传", GREEN_D, GREEN_CARD, size=8)
pill(s, rx + Inches(3.30), Inches(5.52), Inches(1.70), Inches(0.30), "61.1 tok/s", BLUE_D, BLUECARD, size=8)
footer(s, 3, "来源：App Store 主流云端助手形态观察 · 本项目 iPhone 18 Pro Max 真机实测（2026-11-03）")
conclusion(s, "AI 机会 = 小模型量化到 1.3GB 后，手机本地实时推理第一次变得可用。")

# ---------------- S4 解决方案与核心功能
s = new_slide(prs)
title_block(s, "解决方案 · 一个完全离线的手机 AI 助手",
            "核心功能：本地对话、工具调用、写操作人确认、模型与上下文可选；Demo 场景 = 日历")
textbox(s, M, Inches(1.38), Inches(7.2), Inches(0.3),
        [[("Demo 一句话：", 10.5, True, BLUE), ("「家长会，明天下午三点，学校，约一小时」", 10.5, True, DARK)]], space_after=0)
fit_image(s, fig("F6-使用方法.png"), M, Inches(1.75), Inches(7.15), Inches(4.03), top_align=True)
textbox(s, M, Inches(5.86), Inches(7.15), Inches(0.45),
        [[("全程飞行模式：本地模型理解 → 结构化工具指令 → 系统确认 → 写入 iOS 日历 → 结果卡", 9.5, False, MID)]], space_after=0)

cards = [
    ("完全离线", "模型权重与推理都在手机；飞行模式下对话、工具调用完整跑通。", GREEN_D),
    ("工具闭环", "日历 / 提醒事项真实写入系统，写后回读校验；不是聊天，是把事办成。", BLUE_D),
    ("人确认", "写操作前弹系统确认框，显示可读日期；用户点「允许」才执行。", ORANGE_D),
    ("模型库 / 档位", "0.6B / 1.7B 自由切换；4K–32K 上下文、四档速度，逐项标清代价。", MID),
]
cw, ch = Inches(2.34), Inches(1.85)
for i, (t, d, c) in enumerate(cards):
    x = Inches(7.95) + (cw + Inches(0.15)) * (i % 2)
    y = Inches(1.75) + (ch + Inches(0.14)) * (i // 2)
    rect(s, x, y, cw, ch, fill=WHITE, line=HAIR, line_w=0.8)
    rect(s, x, y, cw, Inches(0.07), fill=c, round_=False)
    textbox(s, x + Inches(0.18), y + Inches(0.22), cw - Inches(0.36), ch - Inches(0.34),
            [[(t, 12.5, True, c)], [(d, 9.2, False, MID)]], space_after=3)
textbox(s, Inches(7.95), Inches(5.86), Inches(4.83), Inches(0.45),
        [[("PIPL：用户数据不出设备，不收集、不存储对话内容。", 9.5, True, GREEN_D)]], space_after=0)
footer(s, 4, "来源：iOS 演示壳（EngineKit）真机流程 · EventKit 本地写入 · 模型库/档位选择 v1")
conclusion(s, "断网也能把事办成——这是云端助手给不了的体验。")

# ---------------- S5 美高课程特训
s = new_slide(prs)
title_block(s, "美高课程特训 · 从通用模型到「懂美高数学」的专用模型",
            "数据全部自建：真题转化 + 教师合成 + SymPy 符号验真；训练排队中，验收以真题正确率为门禁")
stages = [
    ("真题转化", "21 道 AP FRQ（80% 训练 / 20% holdout）· 用户逐题切题确认"),
    ("教师合成", "10M tokens：ap_calc 40% / precalc 20% / stats 15% / IELTS 25%"),
    ("符号验真", "SymPy 对拍首轮抓出 110 条违规；300 条数值变式 0 错"),
    ("SFT 训练", "起点 SFT17 · 3 epochs · 1.7B 双卡 · WSD 调度（LR 消融后开训）"),
    ("验收门禁", "AP Calc BC 12 题 / 108 分 + holdout ≥85% 才进发布链"),
]
yy = Inches(1.48)
for i, (t, d) in enumerate(stages, 1):
    rect(s, M, yy, Inches(6.95), Inches(0.82), fill=CARD if i % 2 else WHITE, line=None)
    rect(s, M + Inches(0.16), yy + Inches(0.22), Inches(0.38), Inches(0.38), fill=BLUE, line=None, radius=0.5)
    textbox(s, M + Inches(0.16), yy + Inches(0.28), Inches(0.38), Inches(0.26),
            [[(str(i), 10.5, True, WHITE)]], align=PP_ALIGN.CENTER, space_after=0)
    textbox(s, M + Inches(0.70), yy + Inches(0.10), Inches(6.05), Inches(0.65),
            [[(t, 11.8, True, DARK)], [(d, 9.2, False, MID)]], space_after=1)
    if i < 5:
        arrow_down(s, M + Inches(3.38), yy + Inches(0.83), color=RGBColor(0x9C, 0xCB, 0xFF))
    yy += Inches(0.92)
rect(s, Inches(7.75), Inches(1.48), Inches(5.03), Inches(1.08), fill=GREEN_CARD, line=None)
textbox(s, Inches(7.92), Inches(1.58), Inches(4.7), Inches(0.9),
        [[("已上线 · SFT17（日常 + 工具）", 11.5, True, GREEN_D)],
         [("2764 步 · eval 0.535 · 工具调用 90–97.5% · 真机峰值 1.9GB", 8.8, False, MID)]], space_after=2)
rect(s, Inches(7.75), Inches(2.68), Inches(5.03), Inches(1.18), fill=ORANGE_CARD, line=None)
textbox(s, Inches(7.92), Inches(2.78), Inches(4.7), Inches(1.0),
        [[("在训 · SFT19（美高课程）", 11.5, True, ORANGE_D)],
         [("10M tokens 已合成；当前 AP Calc BC 基线 0/108；训练完成后按真题验收", 8.8, False, MID)],
         [("训练中，不提前宣称提升", 8.5, True, ORANGE_D)]], space_after=2)
section_label(s, Inches(7.75), Inches(4.02), Inches(5.0), "SFT17 训练曲线（2764 步 · eval 0.535）")
fit_image(s, fig("C4-训练曲线.png"), Inches(7.75), Inches(4.28), Inches(4.95), Inches(1.95), top_align=True)
footer(s, 5, "来源：SFT17 评测报告 · SFT19 计划/合成日志（2026-11-03）· AP Calc BC 私有真题基线（0/108）")
conclusion(s, "不追求通用榜单——只在我们真正要用的美高课程上，用真题验收。")

# ---------------- S6 实现方式与设备适配
s = new_slide(prs)
title_block(s, "实现方式 · 自研引擎把 1.7B 装进 iPhone，并适配不同机型",
            "底座用 llama.cpp，价值在训练、引擎、工具链、评测四条线全部自己做")
ax, aw = M, Inches(6.3)
rect(s, ax, Inches(1.48), aw, Inches(1.22), fill=BLUECARD, line=RGBColor(0x9C, 0xCB, 0xFF), line_w=0.8)
textbox(s, ax + Inches(0.18), Inches(1.58), aw - Inches(0.36), Inches(0.3),
        [[("App 层 · SwiftUI 演示壳", 12, True, BLUE_D)]], space_after=0)
for i, t in enumerate(["本地对话", "日历/提醒工具", "模型库", "档位选择"]):
    pill(s, ax + Inches(0.18) + Inches(1.53) * i, Inches(2.02), Inches(1.38), Inches(0.34),
         t, BLUE_D, WHITE, size=8.2, bold=False)
arrow_down(s, ax + aw / 2 - Inches(0.09), Inches(2.74), w=Inches(0.18), h=Inches(0.16), color=BLUE)
rect(s, ax, Inches(2.94), aw, Inches(1.95), fill=BLUECARD, line=RGBColor(0x9C, 0xCB, 0xFF), line_w=0.8)
textbox(s, ax + Inches(0.18), Inches(3.04), aw - Inches(0.36), Inches(0.3),
        [[("EngineKit 引擎层 · 全 Swift", 12, True, BLUE_D)]], space_after=0)
chips = ["KV 逐轮清理", "内存预算", "速度档位", "ToolLoop 白名单", "schema 校验", "确认等待"]
for i, t in enumerate(chips):
    x = ax + Inches(0.18) + Inches(2.03) * (i % 3)
    y = Inches(3.44) + Inches(0.50) * (i // 3)
    pill(s, x, y, Inches(1.88), Inches(0.38), t, DARK, WHITE, size=8.5, bold=False)
arrow_down(s, ax + aw / 2 - Inches(0.09), Inches(4.93), w=Inches(0.18), h=Inches(0.16), color=LIGHT)
rect(s, ax, Inches(5.13), aw, Inches(0.88), fill=CARD, line=None)
textbox(s, ax + Inches(0.18), Inches(5.24), aw - Inches(0.36), Inches(0.65),
        [[("llama.cpp 底座 · MIT", 11.5, True, DARK)],
         [("钉版本 · Metal · GGUF · 只作黑盒推理内核，不碰 C kernel", 8.8, False, MID)]], space_after=1)

section_label(s, Inches(7.15), Inches(1.42), Inches(5.6), "真机实测（PM = Pro Max · 4K · 均衡 · 4 轮取后 3 轮）")
bw = [Inches(1.55), Inches(1.20), Inches(1.20), Inches(1.45)]
brows = [
    ["档位", "17 PM", "18 PM", "峰值(18)"],
    ["1.7B Q4_K_M", "38.5", [("61.1", 9.2, True, BLUE_D)], "1903 MB"],
    ["1.7B Q5_K_M", "34.2", "56.5", "2054 MB"],
    ["1.7B Q8_0", "27.3", "40.1", "2683 MB"],
    ["0.6B Q5_K_M", "86.9", "100.5", "1187 MB"],
    ["0.6B Q4_K_M", "89.0", "119.7", "1144 MB"],
    ["0.6B IQ4_XS", "96.7", "121.1", "1109 MB"],
]
table(s, Inches(7.15), Inches(1.70), bw, brows, Inches(0.40), header=True, aligns=["left", "center", "center", "center"], size=9.0)
mx = Inches(7.15)
mws = [Inches(1.78), Inches(1.78), Inches(1.78)]
for i, (v, l, c) in enumerate([
        ("61.1 tok/s", "1.7B Q4 · 18 PM", BLUE),
        ("1.90 GB", "1.7B Q4 峰值", ORANGE_D),
        ("121.1 tok/s", "0.6B IQ4 · 18 PM", GREEN_D)]):
    metric(s, mx + (mws[i] + Inches(0.14)) * i, Inches(4.78), mws[i], Inches(0.86),
           v, l, c, value_size=13)
textbox(s, Inches(7.15), Inches(5.78), Inches(5.6), Inches(0.40),
        [[("内存档位 4K / 8K / 16K / 32K → KV 约 0.44 / 0.88 / 1.75 / 3.5 GB；8GB 机型建议 ≤8K。", 8.8, False, MID)]],
        space_after=0)
footer(s, 6, "来源：EngineKit 源码 · docs/评测/真机跑分对比-17ProMax-vs-18ProMax-20261103.md")
conclusion(s, "同一套代码覆盖 0.6B / 1.7B、4K–32K、四档速度——18 Pro Max 上 1.7B 稳定 61.1 tok/s。")

# ---------------- S7 测试① 工具调用
s = new_slide(prs)
title_block(s, "测试 ① · 工具调用：40 题逐题可查，训练分布 30/30 全过",
            "命题书要求「用测试证明有没有用」——每一次工具调用都落成 case 文件")
fit_image(s, fig("C1-工具调用.png"), M, Inches(1.52), Inches(7.0), Inches(3.50), top_align=True)
rect(s, M, Inches(5.12), Inches(7.0), Inches(0.98), fill=BLUECARD, line=None)
textbox(s, M + Inches(0.20), Inches(5.22), Inches(6.6), Inches(0.80),
        [[("真机回归 12/12 · 21 秒 · 解码 39–49.5 tok/s · 峰值 1852MB", 11, True, BLUE_D)],
         [("覆盖：4 条日历工具 / 4 条聊天 / 2 条路由 / 1 条多轮 / 1 条性能", 8.8, False, MID)]],
        space_after=2)
rx, rw = Inches(7.75), Inches(5.03)
for i, (v, l, n, c) in enumerate([
        ("40 题", "30 训练分布 + 10 泛化", "逐题 case 归档，可复核", BLUE_D),
        ("90–97.5%", "三档 schema 通过率", "训练分布题 100% 通过", BLUE_D),
        ("30/30", "训练分布题全过", "Q8 / Q5 / Q4 三档一致", GREEN_D)]):
    metric(s, rx, Inches(1.52) + Inches(0.96) * i, rw, Inches(0.88), v, l, c,
           value_size=14, note=n)
rect(s, rx, Inches(4.50), rw, Inches(1.60), fill=ORANGE_CARD, line=None)
textbox(s, rx + Inches(0.18), Inches(4.52), rw - Inches(0.36), Inches(1.5),
        [[("失分点：10 道泛化题（唯一）", 10.5, True, ORANGE_D)],
         [("① 相对日期没把握 → 输出 X 占位符，被 schema 拒绝", 8.8, False, DARK)],
         [("② 把确认话术当主路径 → 不调用工具，直接说「已添加」", 8.8, False, DARK)],
         [("已定位：SFT19 合成全量注入「今天」锚点修复", 8.8, True, ORANGE_D)]], space_after=2)
footer(s, 7, "来源：docs/评测/SFT17评测报告-1.7B.md §三 · 演示壳 Harness 12/12（2026-11-03）")
conclusion(s, "训练分布 100% 通过；泛化失败已逐条定位——不是「感觉能用」，是逐题可复核。")

# ---------------- S8 测试② 幻觉与原版对拍
s = new_slide(prs)
title_block(s, "测试 ② · 幻觉率与原版对拍：先量化「错」，再决定怎么兜底",
            "日期题 + 事实编造 + 同档位原版对照，全部实测")
fit_image(s, fig("C2-幻觉率.png"), M, Inches(1.58), Inches(6.0), Inches(3.43), top_align=True)
textbox(s, M, Inches(5.12), Inches(6.0), Inches(0.65),
        [[("日期映射 15 题：无锚点 0/15 → 注入「今天是…」后 9/15。", 9.5, False, MID)],
         [("相对日期 7/9、绝对日期 2/6；仍有 6 题错。", 9.5, False, MID)]], space_after=2)
rx, rw = Inches(6.85), Inches(5.93)
for i, (v, l, c) in enumerate([
        ("12.29 → 5.42", "目标域 PPL（2.3× 更低）", BLUE_D),
        ("41.20 → 17.58", "通用域 PPL（2.2× 更低）", BLUE_D),
        ("14 → 0 题", "15 题生成问题（复读/截断/空答）", GREEN_D)]):
    metric(s, rx, Inches(1.52) + Inches(0.90) * i, rw, Inches(0.80), v, l, c, value_size=14)
rect(s, rx, Inches(4.30), rw, Inches(1.80), fill=ORANGE_CARD, line=None)
textbox(s, rx + Inches(0.18), Inches(4.40), rw - Inches(0.36), Inches(1.62),
        [[("幻觉没有归零：6/15 仍错", 10.5, True, ORANGE_D)],
         [("相对日期短语 / 绝对日期丢失 / 补零不一致 / 采样随机 / 训练期无锚点", 8.8, False, DARK)],
         [("对策：SFT19 全量锚点 + 推理侧注入今天日期 + 高危操作人确认", 8.8, True, BLUE_D)],
         [("不是「模型不会算」，是缺少参照系——产品必须承认并兜底。", 8.8, False, MID)]], space_after=2)
footer(s, 8, "来源：docs/评测/SFT17评测报告-1.7B.md §四/§五 · 同 Q8_0 档、同 256 max-tokens 对拍")
conclusion(s, "训练把目标域拉进可用区间，但幻觉没有归零——所以产品必须有确认与兜底。")

# ---------------- S9 风险与人的角色
s = new_slide(prs)
title_block(s, "风险与人的角色 · AI 判断错了，产品怎么办",
            "命题书完成重点：怎样提醒使用者、由谁确认和处理")
cards = [
    ("① 幻觉可量化", "日期题 0/15→9/15；编造诱导 5 题中 1 题编造。没把握时输出占位符，schema 直接拦截。", BLUE_D),
    ("② 写操作人确认", "日历/提醒写入前弹系统确认；确认框显示可读日期，过期时间给出警告。", GREEN_D),
    ("③ 白名单 + schema", "只能调用注册工具；参数经 schema 校验，编造工具名被拒绝且记录原因。", ORANGE_D),
    ("④ 失败可见", "12 条回归逐条断言；executed/rejected/failed 状态写结果卡与日志，不静默。", MID),
]
cw, ch = Inches(2.95), Inches(1.62)
for i, (t, d, c) in enumerate(cards):
    x = M + (cw + Inches(0.14)) * i
    rect(s, x, Inches(1.42), cw, ch, fill=WHITE, line=HAIR, line_w=0.8)
    rect(s, x, Inches(1.42), cw, Inches(0.06), fill=c, round_=False)
    textbox(s, x + Inches(0.16), Inches(1.58), cw - Inches(0.32), ch - Inches(0.24),
            [[(t, 11.5, True, c)], [(d, 8.6, False, DARK)]], space_after=2)

textbox(s, M, Inches(3.18), CONTENT_W, Inches(0.28),
        [[("风险 → 提醒方式 → 谁确认/处理（命题书完成重点）", 11.5, True, DARK)]], space_after=0)
risk_rows = [
    ["风险", "产品怎么提醒", "谁确认/处理"],
    ["日期 / 事实幻觉", "占位符被 schema 拦截；结果卡标注「不确定」，不执行写入", "使用者本人"],
    ["时间 / 地点写错", "系统确认框显示可读日期与过期警告；确认后才写入", "使用者本人"],
    ["模型编造工具", "白名单拒绝，返回失败原因并记日志", "使用者本人（可见失败）"],
    ["模型答不上来", "明确说「不知道」，不硬编；有网可回退云端（规划）", "使用者本人"],
]
table(s, M, Inches(3.46), [Inches(2.55), Inches(6.35), Inches(3.33)],
      risk_rows, Inches(0.38), header=True, size=8.8)
textbox(s, M, Inches(5.52), CONTENT_W, Inches(0.62),
        [[("当前限制（诚实披露）：", 9.5, True, ORANGE_D),
          ("1.7B 复杂推理仍有限 · 工具库只有日历/提醒 · Android 未覆盖 · 美高课程模型训练中 · 日期幻觉仍有 6/15 错", 9, False, DARK)],
         [("高风险操作必须人工确认；模型没把握时明确说「不知道」，不硬编；有网可回退云端（规划中）。", 9, False, MID)]],
        space_after=2)
footer(s, 9, "来源：ToolKit 白名单/schema 实现 · 12 条回归用例 · 日期评测 15 题（SFT17 报告）")
conclusion(s, "红线：AI 只提供建议与结构化结果，最终决定权永远在人。")

# ---------------- S10 团队与资源
s = new_slide(prs)
title_block(s, "团队分工、AI 工具与第三方资源", "命题书硬性覆盖项 + 接下来的路线")
lx, lw = M, Inches(6.05)
section_label(s, lx, Inches(1.40), lw, "团队分工（按实际填写）")
textbox(s, lx, Inches(1.66), lw, Inches(1.55),
        [[("引擎运行时（EngineKit）：＿＿＿＿＿＿＿＿", 10, False, DARK)],
         [("模型训练与数据合成：＿＿＿＿＿＿＿＿", 10, False, DARK)],
         [("iOS App 与演示：＿＿＿＿＿＿＿＿＿＿", 10, False, DARK)],
         [("评测与回归：＿＿＿＿＿＿＿＿＿＿＿＿", 10, False, DARK)],
         [("产品与测试：＿＿＿＿＿＿＿＿＿＿＿＿", 10, False, DARK)]], space_after=3)
section_label(s, lx, Inches(3.24), lw, "AI 工具使用说明")
textbox(s, lx, Inches(3.50), lw, Inches(0.95),
        [[("训练数据：云端教师大模型合成 + SymPy 后验 + 锚点/格式质检", 9.2, False, DARK)],
         [("真题转化：官方 CodeBuddy CLI（云端大模型）", 9.2, False, DARK)],
         [("开发辅助：编码/文档 AI 协作，对话与提示词可导出", 9.2, False, DARK)]], space_after=2)
section_label(s, lx, Inches(4.50), lw, "第三方资源")
textbox(s, lx, Inches(4.76), lw, Inches(0.75),
        [[("llama.cpp（MIT）· Qwen3 开源模型（Apache 2.0）", 9.2, False, DARK)],
         [("公开中文语料 · iOS EventKit / SwiftUI 系统框架", 9.2, False, DARK)]], space_after=2)
rect(s, lx, Inches(5.55), lw, Inches(0.78), fill=BLUECARD, line=None)
textbox(s, lx + Inches(0.16), Inches(5.62), lw - Inches(0.32), Inches(0.66),
        [[("模型口径：", 8.8, True, BLUE_D),
          ("基于 Qwen3 开源模型继续训练，不称自研；提交物 = 10 页 PPT + ≤8 分钟真机 Demo 视频。", 8.8, False, DARK)],
         [("可复现：GitHub Release · 评测脚本 · 12 条回归 · 双机跑分报告，全部随仓库提供。", 8.8, False, MID)]],
        space_after=1)

rx, rw = Inches(6.85), Inches(5.93)
section_label(s, rx, Inches(1.40), rw, "路线（已实现 / 进行中 / 规划）")
steps = [
    ("SFT19 美高课程训练", "排队中 · 美高数学 3 epochs", ORANGE_D, ORANGE_CARD),
    ("量化 + 真题验收", "待训练完成 · AP Calc BC ≥85% 门禁", MID, RGBColor(0xEC, 0xEC, 0xF0)),
    ("TestFlight 分发", "外壳已具备 · 模型库/导入/关于与隐私", GREEN_D, GREEN_CARD),
    ("Android 端", "规划中 · 端侧多平台", MID, RGBColor(0xEC, 0xEC, 0xF0)),
    ("本地多 Agent", "M5+ · 1.7B 领队 + 0.6B 工人", BLUE_D, BLUECARD),
]
yy = Inches(1.68)
for i, (t, d, c, fill) in enumerate(steps, 1):
    rect(s, rx, yy, rw, Inches(0.72), fill=fill, line=None)
    rect(s, rx + Inches(0.14), yy + Inches(0.18), Inches(0.36), Inches(0.36), fill=c, line=None, radius=0.5)
    textbox(s, rx + Inches(0.14), yy + Inches(0.23), Inches(0.36), Inches(0.25),
            [[(str(i), 9.5, True, WHITE)]], align=PP_ALIGN.CENTER, space_after=0)
    textbox(s, rx + Inches(0.64), yy + Inches(0.12), rw - Inches(0.78), Inches(0.55),
            [[(t, 10.8, True, DARK)], [(d, 8.8, False, MID)]], space_after=1)
    yy += Inches(0.82)
textbox(s, rx, Inches(5.95), rw, Inches(0.35),
        [[("GitHub：github.com/fanyifan090409-dev/mobile-llm-engine", 9, False, MID)]], space_after=0)
footer(s, 10, "来源：项目仓库 · 训练/评测日志 · 第三方许可证（MIT / Apache 2.0）")
conclusion(s, "把 AI 从云端搬进口袋，让数据留在学生自己手里。")

prs.save(OUT)
print("PPTX v3 saved:", OUT)
