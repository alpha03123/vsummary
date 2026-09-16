"""AI 视频笔记提示词与风格预设。"""

from __future__ import annotations


NOTE_TEMPLATES: dict[str, dict[str, str]] = {
    "general": {"label": "通用", "instruction": "结构清晰，兼顾重点、细节和可复习性。"},
    "short": {"label": "短笔记", "instruction": "只记录最重要的结论、事实和步骤，保持紧凑。"},
    "long": {"label": "长笔记", "instruction": "完整记录各主题的重要论述、例子和步骤，不遗漏关键内容。"},
    "minimal": {"label": "精简", "instruction": "只记录最重要的结论、事实和步骤，保持简洁。"},
    "detailed": {"label": "详细", "instruction": "完整记录各主题的重要论述、例子和步骤，不遗漏关键内容。"},
    "tutorial": {"label": "教程", "instruction": "按操作顺序整理，突出前提、步骤、关键点、结果和常见边界。"},
    "academic": {"label": "学术", "instruction": "使用正式、客观的表达，清晰区分概念、论据、方法和结论。"},
    "task_oriented": {"label": "任务导向", "instruction": "突出目标、待办、决策、负责人或下一步；没有证据时不要虚构。"},
    "business": {"label": "商业风格", "instruction": "突出问题、判断依据、方案、风险、指标和行动建议。"},
    "meeting_minutes": {"label": "会议纪要", "instruction": "按议题整理讨论、结论、待办和待确认事项；没有证据时不要补写负责人或截止时间。"},
    "life_journal": {"label": "生活向", "instruction": "以自然、亲切的方式记录经历、感受和可借鉴的实践，但不添加视频之外的感受。"},
    "xiaohongshu": {"label": "小红书", "instruction": "使用易读、有吸引力的标题和短段落，可适量使用 emoji；优先保证事实准确，避免夸大。"},
}

# 供既有 Agent 导入路径使用；直接生成 AI 笔记改用 NOTE_TEMPLATES。
NOTE_LENGTH_INSTRUCTIONS = {
    "long": NOTE_TEMPLATES["long"]["instruction"],
    "short": NOTE_TEMPLATES["short"]["instruction"],
}


def build_ai_note_prompt(*, title: str, transcript_text: str, template: str = "general", summary_text: str = "") -> str:
    """构建直接生成 AI 笔记时使用的简洁提示词。"""
    resolved_template = NOTE_TEMPLATES.get(template, NOTE_TEMPLATES["general"])
    summary_section = f"\n已有概况（仅作辅助，仍以转写为准）：\n{summary_text.strip()}\n" if summary_text.strip() else ""
    return (
        "你是专业的视频笔记助手。根据视频转写整理一份中文 Markdown 笔记。\n"
        f"视频标题：{title}\n"
        f"笔记风格：{resolved_template['label']}。{resolved_template['instruction']}\n\n"
        "要求：\n"
        "- 只输出最终 Markdown，不要代码块或说明。\n"
        "- 删除寒暄、广告、重复和无关内容；保留重要事实、例子、结论和明确建议。\n"
        "- 用二级、三级标题和必要的列表或表格组织内容；时间点仅在转写明确提供且确有助益时保留。\n"
        "- 不补造视频没有提到的事实、数据、案例、建议或待办。\n"
        f"{summary_section}\n视频转写：\n---\n{transcript_text.strip()}\n---"
    )


def build_note_length_instruction(note_length: str) -> str:
    """兼容 Agent 保存笔记时的简短写作要求。"""
    template = "long" if note_length == "long" else "short"
    return NOTE_TEMPLATES[template]["instruction"]
