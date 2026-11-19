"""
==============================================================================
模块名称: core/trace_logger.py
功能描述: 智能体底座与大模型多轮交互维测轨迹追踪器 (Harness Trace Logger)
          负责以单文件文本 (`agent_debug.txt`) 形式结构化记录：
          1. System Prompt (系统指令)
          2. 历史对话上下文 (History Dialog Context)
          3. 当前注册的可用工具列表 (Available Tools)
          4. 本轮实际触发的工具与检索切片明细 (Invoked Tools & Retrieval)
          5. 发送给大模型的当前轮次最终 Prompt
          6. 大模型原始返回的自然语言回答与元数据
          
          内置机制：
          - 支持 .env 总开关一键开启/关闭 (关时 0 额外耗时与 0 磁盘 I/O)；
          - 内置 10MB 自动轮转滚动与备份清理机制 (默认保留最多 2 份，彻底杜绝日志无限膨胀)；
          - 纯 Python 原生 logging.handlers 库实现，零外部依赖。
==============================================================================
"""

import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

import config


@dataclass
class HarnessTraceContext:
    """
    单次提问全生命周期的完整交互轨迹上下文
    记录 Harness 调度底座与 LLM 之间的往返全要素
    """
    query: str                                                 # 原始用户提问
    session_id: str = "default_user"                           # 会话 ID
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    system_prompt: str = ""                                    # 注入的系统设定
    history_dialog: List[Dict[str, str]] = field(default_factory=list)  # 前序历史对话
    available_tools: List[str] = field(default_factory=list)   # 注册可用的工具能力列表
    invoked_tools: List[Dict[str, Any]] = field(default_factory=list)   # 本轮实际调用的工具明细
    current_prompt: str = ""                                   # 本轮组装后发给 LLM 的 Payload
    llm_config: Dict[str, Any] = field(default_factory=dict)   # 模型参数 (型号、温度等)
    ai_response: str = ""                                      # LLM 原始完成内容
    execution_time_ms: float = 0.0                             # 全流程端到端耗时 (毫秒)


class HarnessTraceLogger:
    """
    维测日志管理器
    基于 RotatingFileHandler 实现安全的 10MB 自动轮转与定量清理
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        log_file: Optional[Path] = None,
        max_mb: Optional[int] = None,
        backup_count: Optional[int] = None
    ) -> None:
        self.enabled = config.AGENT_DEBUG if enabled is None else enabled
        self.log_file = log_file or config.AGENT_DEBUG_FILE
        self.max_mb = max_mb or config.AGENT_DEBUG_MAX_MB
        self.backup_count = backup_count if backup_count is not None else config.AGENT_DEBUG_BACKUP_COUNT

        self._logger: Optional[logging.Logger] = None
        if self.enabled:
            self._init_logger()

    def _init_logger(self) -> None:
        """初始化基于文件大小轮转的 Python 日志对象"""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = self.max_mb * 1024 * 1024  # 转换为字节 (10MB)

        logger_name = f"HarnessTrace_{id(self)}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        # 清除已有的 handlers 避免重复
        for h in list(logger.handlers):
            logger.removeHandler(h)

        # 核心：使用 RotatingFileHandler 自动处理 10MB 滚动与最多 2 份备份淘汰
        handler = RotatingFileHandler(
            filename=str(self.log_file),
            maxBytes=max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8"
        )
        # 纯净输出格式 (由我们自行排版完整大块)
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self._logger = logger

    def record_trace(self, trace: HarnessTraceContext) -> None:
        """
        将单次交互的完整六大维度信息格式化追加至日志文件
        如果维测未开启，直接快速返回，0 额外开销
        """
        if not self.enabled:
            return

        if self._logger is None:
            self._init_logger()

        formatted_block = self._format_trace_block(trace)
        if self._logger:
            self._logger.info(formatted_block)

    @staticmethod
    def _format_trace_block(trace: HarnessTraceContext) -> str:
        """排版生成直观、易读、带编号的结构化维测块"""
        lines = [
            "#" * 80,
            f"[AGENT HARNESS TRACE] 用户提问: \"{trace.query}\"",
            f"记录时间: {trace.timestamp} | 会话ID: {trace.session_id} | 端到端耗时: {trace.execution_time_ms:.1f}ms",
            "#" * 80,
            "",
            "【1. SYSTEM PROMPT (系统指令)】",
            trace.system_prompt.strip() if trace.system_prompt else "(无 System Prompt)",
            "",
            "【2. 历史对话记录 (HISTORY DIALOG)】"
        ]

        if trace.history_dialog:
            for turn in trace.history_dialog:
                role = turn.get("role", "unknown").upper()
                content = turn.get("content", "").replace("\n", " ")
                lines.append(f"  [{role}]: {content[:150]}{'...' if len(content) > 150 else ''}")
        else:
            lines.append("  (本轮为首轮对话，无前序历史记录)")

        lines.extend([
            "",
            "【3. 可用工具列表 (AVAILABLE TOOLS)】"
        ])
        for tool in trace.available_tools:
            lines.append(f"  • {tool}")

        lines.extend([
            "",
            "【4. 本轮实际调用的工具与结果 (INVOKED TOOLS & RETRIEVAL)】"
        ])
        if trace.invoked_tools:
            for call in trace.invoked_tools:
                lines.append(f"  • 工具名称: {call.get('tool')}")
                if "keywords" in call:
                    lines.append(f"    - 提取关键词: {call.get('keywords')}")
                if "retrieved_chunks" in call:
                    chunks = call.get("retrieved_chunks", [])
                    lines.append(f"    - 召回切片数: {len(chunks)} 个")
                    for idx, c in enumerate(chunks, 1):
                        lines.append(f"      {idx}. [{c.get('source_filename')}] {c.get('location_label')} (得分: {c.get('score', 0):.4f})")
        else:
            lines.append("  (本轮未调用任何检索或扩展工具)")

        lines.extend([
            "",
            "【5. 当前发给 LLM 的最终 PROMPT (CURRENT TURN PROMPT)】",
            trace.current_prompt.strip() if trace.current_prompt else "(无当前轮次 Prompt)",
            "",
            "【6. AI 最终返回的自然语言回答 (AI RESPONSE)】",
            trace.ai_response.strip() if trace.ai_response else "(AI 返回内容为空)",
            "",
            "【7. LLM 调用配置】",
            f"  • 模型: {trace.llm_config.get('model', 'default')} | 温度: {trace.llm_config.get('temperature', 'default')} | 提供商: {trace.llm_config.get('provider', 'default')}",
            "#" * 80,
            "\n"
        ])

        return "\n".join(lines)
