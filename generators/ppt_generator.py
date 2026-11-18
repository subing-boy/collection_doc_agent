"""
==============================================================================
模块名称: generators/ppt_generator.py
功能描述: PowerPoint 演示文稿 (.pptx) 逆向生成引擎
          基于结构化 Slide JSON 数据，运用现代 16:9 商业宽屏版式排版规则，
          自动渲染包含：封面页、多卡片结构页、核心结论页等专业视觉幻灯片。
可移植性: 依赖 python-pptx，内置颜色与坐标常量，无需外置模板文件。
==============================================================================
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

import config


# ==============================================================================
# 设计系统常量定义 (现代 16:9 视觉调色板与排版规范)
# ==============================================================================
COLOR_PRIMARY_DARK = RGBColor(0x0F, 0x17, 0x2A)     # 深度石墨青黑 (用于主标题)
COLOR_BRAND_BLUE = RGBColor(0x25, 0x63, 0xEB)       # 科技亮蓝 (用于重点标识与副标)
COLOR_CARD_BG = RGBColor(0xF1, 0xF5, 0xF9)          # 浅灰底卡片背景
COLOR_TEXT_MAIN = RGBColor(0x1E, 0x29, 0x3B)        # 灰黑色 (用于正文)
COLOR_TEXT_MUTED = RGBColor(0x64, 0x74, 0x8B)       # 灰蓝色 (用于次要说明与出处)
COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)            # 纯白

FONT_NAME = "Microsoft YaHei"                       # 统一跨平台中文字体


class PPTGenerator:
    """
    PowerPoint 演示文稿生成器
    负责将大模型提炼的结构化知识转化为精美的 16:9 演示文稿
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or config.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_presentation(
        self,
        deck_title: str,
        deck_subtitle: str,
        slides_data: List[Dict[str, Any]],
        output_filename: Optional[str] = None
    ) -> Path:
        """
        根据幻灯片数组生成 PPTX 文件
        
        :param deck_title: 演示文稿总标题
        :param deck_subtitle: 副标题或背景说明
        :param slides_data: 幻灯片内容列表，格式示例:
            [
                {
                    "type": "content_cards",        # 类型: content_cards / summary
                    "title": "系统架构关键突破",
                    "takeaway": "核心结论: 采用轻量化本地向量库实现毫秒级溯源",
                    "cards": [
                        {
                            "card_title": "精密切片",
                            "points": ["PPT 逐页包含演讲者备注", "Word 保留标题层级面包屑"]
                        },
                        {
                            "card_title": "严格溯源",
                            "points": ["回答强制锁定出处页码", "无依据自动声明未知"]
                        }
                    ]
                }
            ]
        :param output_filename: 指定保存文件名
        :return: 生成的 pptx 绝对路径
        """
        prs = pptx.Presentation()

        # 1. 严格锁定 16:9 现代宽屏比例 (13.333 x 7.5 英寸)
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # 选用空白母版 (Blank Slide Layout)
        blank_slide_layout = prs.slide_layouts[6]

        # 2. 渲染封面页 (Cover Slide)
        self._render_cover_slide(prs, blank_slide_layout, deck_title, deck_subtitle)

        # 3. 逐页渲染内容页
        for slide_info in slides_data:
            stype = slide_info.get("type", "content_cards")
            if stype == "summary":
                self._render_summary_slide(prs, blank_slide_layout, slide_info)
            else:
                self._render_cards_slide(prs, blank_slide_layout, slide_info)

        # 4. 导出保存
        if not output_filename:
            clean_title = "".join(c for c in deck_title if c.isalnum() or c in ("-", "_")).strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{clean_title or '汇报幻灯片'}_{timestamp}.pptx"

        if not output_filename.endswith(".pptx"):
            output_filename += ".pptx"

        target_path = self.output_dir / output_filename
        prs.save(str(target_path))
        return target_path

    def _render_cover_slide(self, prs, layout, title: str, subtitle: str) -> None:
        """渲染高对比度现代封面页"""
        slide = prs.slides.add_slide(layout)

        # 左侧强调色装饰条
        accent_bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.2), Inches(0.15), Inches(2.8)
        )
        accent_bar.fill.solid()
        accent_bar.fill.fore_color.rgb = COLOR_BRAND_BLUE
        accent_bar.line.fill.background()

        # 标题文本框
        tx_box = slide.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(11.0), Inches(3.2))
        tf = tx_box.text_frame
        tf.word_wrap = True

        # 主标题
        p_title = tf.paragraphs[0]
        p_title.text = title
        p_title.font.name = FONT_NAME
        p_title.font.size = Pt(36)
        p_title.font.bold = True
        p_title.font.color.rgb = COLOR_PRIMARY_DARK
        p_title.space_after = Pt(14)

        # 副标题
        if subtitle:
            p_sub = tf.add_paragraph()
            p_sub.text = subtitle
            p_sub.font.name = FONT_NAME
            p_sub.font.size = Pt(16)
            p_sub.font.color.rgb = COLOR_BRAND_BLUE
            p_sub.space_after = Pt(20)

        # 底部元信息
        p_meta = tf.add_paragraph()
        p_meta.text = f"个人文档管家 Agent 自动生成  |  日期: {datetime.now().strftime('%Y-%m-%d')}"
        p_meta.font.name = FONT_NAME
        p_meta.font.size = Pt(11)
        p_meta.font.color.rgb = COLOR_TEXT_MUTED

    def _render_cards_slide(self, prs, layout, data: Dict[str, Any]) -> None:
        """渲染内容卡片页 (2~3 列结构卡片)"""
        slide = prs.slides.add_slide(layout)

        # 1. 顶部标题
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(11.5), Inches(0.8))
        tf_title = title_box.text_frame
        p_title = tf_title.paragraphs[0]
        p_title.text = data.get("title", "未命名章节")
        p_title.font.name = FONT_NAME
        p_title.font.size = Pt(24)
        p_title.font.bold = True
        p_title.font.color.rgb = COLOR_PRIMARY_DARK

        # 2. 核心结论条 (Takeaway Pill)
        takeaway = data.get("takeaway")
        if takeaway:
            p_takeaway = tf_title.add_paragraph()
            p_takeaway.text = f"💡 {takeaway}"
            p_takeaway.font.name = FONT_NAME
            p_takeaway.font.size = Pt(12)
            p_takeaway.font.bold = True
            p_takeaway.font.color.rgb = COLOR_BRAND_BLUE

        # 3. 栅格化多卡片渲染
        cards = data.get("cards", [])
        num_cards = max(1, min(len(cards), 3))  # 最多排版 3 张横向卡片
        
        canvas_left = 0.8
        canvas_top = 2.0
        canvas_width = 11.733
        card_spacing = 0.35
        card_width = (canvas_width - (num_cards - 1) * card_spacing) / num_cards
        card_height = 4.8

        for i, card_info in enumerate(cards[:3]):
            left = canvas_left + i * (card_width + card_spacing)
            # 添加浅色矩形卡片底色
            rect = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(left), Inches(canvas_top),
                Inches(card_width), Inches(card_height)
            )
            rect.fill.solid()
            rect.fill.fore_color.rgb = COLOR_CARD_BG
            rect.line.fill.background()

            # 卡片文本内容
            card_tx = slide.shapes.add_textbox(
                Inches(left + 0.2), Inches(canvas_top + 0.25),
                Inches(card_width - 0.4), Inches(card_height - 0.5)
            )
            ctf = card_tx.text_frame
            ctf.word_wrap = True

            # 卡片标题
            cp_title = ctf.paragraphs[0]
            cp_title.text = card_info.get("card_title", f"要点 {i+1}")
            cp_title.font.name = FONT_NAME
            cp_title.font.size = Pt(16)
            cp_title.font.bold = True
            cp_title.font.color.rgb = COLOR_PRIMARY_DARK
            cp_title.space_after = Pt(12)

            # 卡片项目符号
            for pt in card_info.get("points", []):
                p_pt = ctf.add_paragraph()
                p_pt.text = f"• {pt}"
                p_pt.font.name = FONT_NAME
                p_pt.font.size = Pt(12)
                p_pt.font.color.rgb = COLOR_TEXT_MAIN
                p_pt.space_after = Pt(8)

    def _render_summary_slide(self, prs, layout, data: Dict[str, Any]) -> None:
        """渲染总结与下一步页面"""
        slide = prs.slides.add_slide(layout)

        # 标题
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.8), Inches(11.5), Inches(1.0))
        tf = title_box.text_frame
        p = tf.paragraphs[0]
        p.text = data.get("title", "总结与后续行动")
        p.font.name = FONT_NAME
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = COLOR_PRIMARY_DARK

        # 总结正文框
        body_box = slide.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.3), Inches(4.5))
        btf = body_box.text_frame
        btf.word_wrap = True

        for idx, item in enumerate(data.get("points", []), start=1):
            bp = btf.add_paragraph() if idx > 1 else btf.paragraphs[0]
            bp.text = f"{idx}. {item}"
            bp.font.name = FONT_NAME
            bp.font.size = Pt(15)
            bp.font.color.rgb = COLOR_TEXT_MAIN
            bp.space_after = Pt(14)
