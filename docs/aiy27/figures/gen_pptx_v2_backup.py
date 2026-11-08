#!/usr/bin/env python3
"""AIY 27 PPT 生成 v2（10 页 16:9 原生 PPTX）。

v2 修正（v1 错位根因）：
- 图片一律按真实像素比例「适应内容区」居中放置，绝不超出内容区（v1 全宽图超出幻灯片底边）
- 固定版式网格：标题区 0.42-1.62in / 内容区 1.80-6.95in / 页脚 7.10in，全部常量驱动
- 图内自带结论条与来源注脚（v2 图表），页内不再重复放结论文字
- 双图页统一顶对齐 + 图下配一行说明
用法：.venv/bin/python docs/aiy27/figures/gen_pptx.py
验证：Keynote 打开导出 PDF → scripts/pdf2png.swift → 目检每页
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
GREEN = RGBColor(0x30, 0xD1, 0x58)
ORANGE = RGBColor(0xFF, 0x9F, 0x0A)
HAIR = RGBColor(0xD9, 0xD9, 0xDE)
CARD = RGBColor(0xF5, 0xF5, 0xF7)
BLUECARD = RGBColor(0xEA, 0xF3, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "PingFang SC"

SW, SH = Inches(13.333), Inches(7.5)
M = Inches(0.65)                       # 页边距
ZONE_TITLE_TOP = Inches(0.42)          # 标题区
ZONE_SUB_TOP = Inches(1.10)
ZONE_HAIR_Y = Inches(1.56)
ZONE_TOP = Inches(1.80)                # 内容区
ZONE_BOTTOM = Inches(6.95)
FOOTER_Y = Inches(7.10)


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


def textbox(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(6)
        runs = para if isinstance(para, list) else [para]
        for (t, s, b, c) in runs:
            r = p.add_run()
            r.text = t
            set_font(r, s, b, c)
    return tb


def title_block(slide, title, sub=None):
    textbox(slide, M, ZONE_TITLE_TOP, SW - 2 * M, Inches(0.6),
            [[(title, 27, True, DARK)]])
    if sub:
        textbox(slide, M, ZONE_SUB_TOP, SW - 2 * M, Inches(0.35),
                [[(sub, 12.5, False, MID)]])
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, M, ZONE_HAIR_Y, SW - 2 * M, Pt(1))
    line.fill.solid()
    line.fill.fore_color.rgb = HAIR
    line.line.fill.background()
    line.shadow.inherit = False


def footer(slide, page):
    textbox(slide, M, FOOTER_Y, Inches(5), Inches(0.3),
            [[("AIY 27 · 本地推理引擎 · 题目一（AI×科学工程）", 9, False, LIGHT)]])
    textbox(slide, SW - M - Inches(1), FOOTER_Y, Inches(1), Inches(0.3),
            [[(f"{page:02d}", 9, False, LIGHT)]], align=PP_ALIGN.RIGHT)


def fit_image(slide, path, x, y, w, h, top_align=False):
    """按真实像素比例适配 (x,y,w,h) 框，居中；同比例图 top_align=True 时顶对齐。"""
    iw, ih = png_size(path)
    scale = min(w / iw, h / ih)
    pw, ph = int(iw * scale), int(ih * scale)
    px = x + (w - pw) // 2
    py = y if top_align else y + (h - ph) // 2
    return slide.shapes.add_picture(path, px, py, width=pw, height=ph)


def caption(slide, text, x, y, w):
    textbox(slide, x, y, w, Inches(0.3), [[(text, 11, False, MID)]], align=PP_ALIGN.CENTER)


def photo_placeholder(slide, x, y, w, h, label):
    shp = rect(slide, x, y, w, h, fill=WHITE, line=LIGHT, line_w=1.0)
    shp.line.dash_style = 2
    textbox(slide, x, y + h / 2 - Inches(0.25), w, Inches(0.5),
            [[(label, 13, False, LIGHT)]], align=PP_ALIGN.CENTER)


def fig(slide, name):
    return os.path.join(HERE, name)


# ====================================================================== 页面

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH

# ---------------- S1 封面
s = new_slide(prs)
rect(s, 0, 0, SW, SH, fill=WHITE)
rect(s, M, Inches(4.65), Inches(0.7), Inches(0.08), fill=BLUE, round_=False)
textbox(s, M, Inches(1.35), Inches(11.7), Inches(0.5),
        [[("AIY 27 初级站 · 高中组 Pro 组", 15, True, BLUE)]])
textbox(s, M, Inches(1.95), Inches(11.7), Inches(1.4),
        [[("把 AI 装进口袋", 56, True, DARK)]])
textbox(s, M, Inches(3.25), Inches(11.7), Inches(0.6),
        [[("不联网的手机本地推理引擎", 23, False, DARK)]])
textbox(s, M, Inches(4.85), Inches(11.7), Inches(1.2),
        [[("题目一 · AI×科学工程 · 自定方向：离线与隐私场景", 14.5, False, MID)],
         [("团队：＿＿＿＿＿＿＿＿　　演示人：＿＿＿＿＿＿＿＿", 14.5, False, MID)]])
photo_placeholder(s, SW - M - Inches(2.5), Inches(1.55), Inches(2.5), Inches(2.1), "封面图：真机演示截图")

# ---------------- S2 命题理解与目标用户（问题一句话 + 2026 真实事故表）
s = new_slide(prs)
title_block(s, "命题理解 · 想用 AI 的人，被两件事挡住", "没有网——或者不敢把数据交出去")
rect(s, M, ZONE_TOP, SW - 2 * M, Inches(0.95), fill=BLUECARD, line=BLUE)
textbox(s, M + Inches(0.3), ZONE_TOP + Inches(0.18), SW - 2 * M - Inches(0.6), Inches(0.65),
        [[("问题一句话：", 15.5, True, BLUE),
          ("手机 AI 助手依赖云端大模型——断网即失效，数据出设备。想随时随地用 AI 的人，两头都为难。", 15.5, True, DARK)]])
textbox(s, M, ZONE_TOP + Inches(1.12), SW - 2 * M, Inches(0.62),
        [[("目标用户：网络受限的国际学校学生——教室和宿舍网不稳，查资料、记日程都受影响。", 13, True, DARK)],
         [("我们就是用户：本人每天在受限网络里查资料，同学同款；出国时流量又贵又不稳；日程、健康记录、私人对话不想上传。", 12.5, False, MID)]])
# 事故表：原 F8 场景图与上面文字重复，换成 2026 年真实事故（逐行带来源，投影清晰）
TY = ZONE_TOP + Inches(1.85)
textbox(s, M, TY, SW - 2 * M, Inches(0.32),
        [[("为什么「不敢交出去」——2026 年公开报道的真实事故", 13.5, True, DARK)]])
_cols = [("时间", 1.15), ("事件", 6.35), ("泄漏内容", 2.55), ("来源", 1.98)]
_hx = M
for _name, _w in _cols:
    textbox(s, _hx, TY + Inches(0.34), Inches(_w), Inches(0.26),
            [[(_name, 10.5, True, MID)]])
    _hx += Inches(_w)
_rows = [
    ("2026.04–06", "Claude Code 安全后门", "：未经同意回传地域、身份标识等敏感数据",
     "用户敏感信息", "求是网 / 工信部风险提示", False),
    ("2026.09", "智谱 ZCode 传包风波", "：整个项目连同修改历史打包加密上传云端",
     "3.29 万文件 / 4.11 亿明文字符", "36氪 / 掘金（企业函件称）", True),
    ("2026.08", "PROMPTPEEK 攻击", "：共享缓存侧信道可还原其他用户提问",
     "用户提问内容", "NDSS 2025 论文", False),
    ("2026.08", "Reasoning Trace Theft", "：三家 API 加密推理链缺陷，跨模型重放窃取思维链",
     "思维链 / 推理内容", "CSA 研究 / 绿盟分析", False),
    ("2026 上半年", "法国医院病历事件", "：医生用 Claude 3 写病历，8 个月 1247 份",
     "患者医疗数据", "法媒隐私审计报告", False),
]
_row_h = Inches(0.52)
_ry = TY + Inches(0.62)
for _i, (_t, _ev, _de, _leak, _src, _hot) in enumerate(_rows):
    rect(s, M, _ry, SW - 2 * M, _row_h, fill=CARD if _i % 2 else WHITE, round_=False)
    _hx = M
    textbox(s, _hx + Inches(0.08), _ry, Inches(1.15), _row_h,
            [[(_t, 9.5, False, MID)]], anchor=MSO_ANCHOR.MIDDLE)
    _hx += Inches(1.15)
    textbox(s, _hx + Inches(0.08), _ry, Inches(6.35), _row_h,
            [[(_ev, 10.5, True, DARK), (_de, 10, False, DARK)]], anchor=MSO_ANCHOR.MIDDLE)
    _hx += Inches(6.35)
    textbox(s, _hx + Inches(0.08), _ry, Inches(2.55), _row_h,
            [[(_leak, 9.5, _hot, ORANGE if _hot else DARK)]], anchor=MSO_ANCHOR.MIDDLE)
    _hx += Inches(2.55)
    textbox(s, _hx + Inches(0.08), _ry, Inches(1.98), _row_h,
            [[(_src, 9, False, MID)]], anchor=MSO_ANCHOR.MIDDLE)
    _ry += _row_h
footer(s, 2)

# ---------------- S3 解决方案（F6）
s = new_slide(prs)
title_block(s, "解决方案 · 断网也能用的本地 AI", "打开飞行模式，一句话任务——本地模型理解、调用工具、系统确认、写入日历")
fit_image(s, fig(s, "F6-使用方法.png"), M, ZONE_TOP, SW - 2 * M, ZONE_BOTTOM - ZONE_TOP)
footer(s, 3)

# ---------------- S4 实现方式（F7）
s = new_slide(prs)
title_block(s, "实现方式 · 我们对开源底座做了什么", "底座用开源、工程全自研——训练、引擎、工具链、评测四条线全部自己完成")
fit_image(s, fig(s, "F7-引擎机制.png"), M, ZONE_TOP, SW - 2 * M, ZONE_BOTTOM - ZONE_TOP)
footer(s, 4)

# ---------------- S5 两条模型线（F9）
s = new_slide(prs)
title_block(s, "两条模型线 · 小模型先验证，主力再升级", "0.6B 先跑通全链路，1.7B 承接全部能力——同一套 40 题评测协议（0.6B 单档结构验证、1.7B 三档量化矩阵）")
fit_image(s, fig(s, "F9-两条模型线.png"), M, ZONE_TOP, SW - 2 * M, ZONE_BOTTOM - ZONE_TOP)
footer(s, 5)

# ---------------- S6 设备适配（F10）
s = new_slide(prs)
title_block(s, "设备适配 · 好手机坏手机都能用", "按内存自动选档：低配跑 0.6B 基础任务，主流跑 1.7B 主力档——未来支持多模型自由搭配")
fit_image(s, fig(s, "F10-设备适配.png"), M, ZONE_TOP, SW - 2 * M, ZONE_BOTTOM - ZONE_TOP)
footer(s, 6)

# ---------------- S7 数据与评测 ①（合成单图，杜绝双图重叠）
s = new_slide(prs)
title_block(s, "数据与评测 ① · 训练曲线与工具调用", "评测数字全部真实实测——训练 2764 步全程曲线、工具调用 40 题逐题状态")
fit_image(s, fig(s, "S6-评测①-训练与工具.png"), M, ZONE_TOP, SW - 2 * M, Inches(3.55), top_align=True)
textbox(s, M, ZONE_TOP + Inches(3.78), SW - 2 * M, Inches(0.4),
        [[("左：训练损失 2.53 → 0.48，验证收敛 0.535。　　右：工具调用三档压缩档位通过率 90-95%，训练分布题 30/30 全过。", 13, False, MID)]])
textbox(s, M, ZONE_TOP + Inches(4.25), SW - 2 * M, Inches(0.4),
        [[("为什么可信：逐题状态有原始评测产物可查（case 文件），不是「跑一次取平均」的口径。", 12.5, False, MID)]])
textbox(s, M, ZONE_TOP + Inches(4.72), SW - 2 * M, Inches(0.4),
        [[("真机实测（iPhone 17 Pro Max · 飞行模式无关的全本地推理）：Q4_K_M ~40 / Q5_K_M ~34 / Q8_0 ~27 tok/s，", 12.5, False, MID),
          ("峰值内存 1.8-2.7GB", 12.5, True, DARK),
          ("；双 Mac 参照：M5 Air 72.4 / M5 Pro 92.5 tok/s（16/18 Pro 待补测）。", 12.5, False, MID)]])
footer(s, 7)

# ---------------- S8 数据与评测 ②（合成单图）
s = new_slide(prs)
title_block(s, "数据与评测 ② · 幻觉率与原版对拍", "「AI 判断错了怎么办」先量化「错」在哪——日期题正确率与生成质量都有实测数字")
fit_image(s, fig(s, "S7-评测②-幻觉与对拍.png"), M, ZONE_TOP, SW - 2 * M, Inches(3.55), top_align=True)
textbox(s, M, ZONE_TOP + Inches(3.78), SW - 2 * M, Inches(0.4),
        [[("左：日期题正确率 0/15 → 9/15（60%），还有 6 题是错的。　　右：目标域困惑度 12.29 → 5.42，生成问题 14 → 0 题。", 13, False, MID)]])
textbox(s, M, ZONE_TOP + Inches(4.25), SW - 2 * M, Inches(0.4),
        [[("诚实披露：6 道错题的根因已逐条定位到训练数据（占位符残留 + 训练期没有「今天」参照），下一轮合成已修正。", 12.5, False, MID)]])
footer(s, 8)

# ---------------- S9 AI 错了怎么办：核心进阶点（人确认闭环 + 幻觉量化）
s = new_slide(prs)
title_block(s, "AI 错了怎么办 · 本项目的核心进阶点", "不是空谈「安全」——写操作人确认的闭环机制 + 「错在哪」先量化，两件事都有实测")
cards = [
    ("① 幻觉量化", "日期/事实类问题有实测正确率（0/15 → 9/15）；模型没把握时输出占位符，App 侧校验拦截，不静默执行。", BLUE),
    ("② 写操作人确认", "写日历/提醒前必弹系统确认框——最终决定权永远在人手上。", GREEN),
    ("③ 白名单拦截", "模型只能调用注册过的工具，编造的工具名会被引擎直接拒绝（实测记录可查）。", ORANGE),
    ("④ 由谁确认和处理", "使用者本人。所有输出是结构化结果 + 置信度提示，不是黑盒决定。", DARK),
]
cw2 = (SW - 2 * M - Inches(0.45)) // 4
for i, (t, b, c) in enumerate(cards):
    x = M + i * (cw2 + Inches(0.15))
    rect(s, x, ZONE_TOP + Inches(0.15), cw2, Inches(2.6))
    rect(s, x, ZONE_TOP + Inches(0.15), cw2, Inches(0.09), fill=c, round_=False)
    textbox(s, x + Inches(0.22), ZONE_TOP + Inches(0.42), cw2 - Inches(0.44), Inches(2.2),
            [[(t, 15.5, True, c)],
             [(b, 12.5, False, DARK)]])
rect(s, M, ZONE_TOP + Inches(3.05), SW - 2 * M, Inches(0.75), fill=BLUECARD, line=BLUE)
textbox(s, M + Inches(0.3), ZONE_TOP + Inches(3.26), SW - 2 * M - Inches(0.6), Inches(0.4),
        [[("红线：产品定位为辅助工具——AI 只提供建议，不替人做最终决定。", 14, True, BLUE)]])
footer(s, 9)

# ---------------- S10 团队分工及 AI 工具、第三方资源
s = new_slide(prs)
title_block(s, "团队分工与资源说明", "命题书硬性覆盖项：谁做了什么、用了哪些 AI 工具、第三方资源有哪些")
textbox(s, M, ZONE_TOP + Inches(0.1), Inches(6), Inches(2.3),
        [[("团队分工（按实际填写）", 16, True, DARK)],
         [("引擎运行时（EngineKit）：＿＿＿＿＿＿", 14, False, DARK)],
         [("模型训练与评测：＿＿＿＿＿＿", 14, False, DARK)],
         [("iOS App 与演示：＿＿＿＿＿＿", 14, False, DARK)],
         [("产品与测试：＿＿＿＿＿＿", 14, False, DARK)]])
textbox(s, M + Inches(6.3), ZONE_TOP + Inches(0.1), Inches(5.7), Inches(2.3),
        [[("AI 工具使用说明", 16, True, DARK)],
         [("训练数据合成：云端教师大模型（合成后经锚点/格式质检）", 14, False, DARK)],
         [("开发辅助：编码与文档辅助（AI 协作记录可提交）", 14, False, DARK)],
         [("第三方资源：llama.cpp（MIT）、Qwen3 开源模型（Apache 2.0）、公开训练语料", 14, False, DARK)]])
textbox(s, M, ZONE_TOP + Inches(2.65), SW - 2 * M, Inches(0.4),
        [[("模型口径：对外一律「基于 Qwen3 开源模型继续训练」，不称自研。", 13.5, True, BLUE)]])
photo_placeholder(s, M, ZONE_TOP + Inches(3.25), Inches(3.4), Inches(1.9), "团队合影（1 张）")
photo_placeholder(s, M + Inches(3.7), ZONE_TOP + Inches(3.25), Inches(3.4), Inches(1.9), "工作过程照（1 张）")
footer(s, 10)

prs.save(OUT)
print("PPTX v2 saved:", OUT)
