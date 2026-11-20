"""
==============================================================================
模块名称: config.py
功能描述: 全局配置管理模块
          包含大模型接入参数、文件物理存储路径、默认分类标签以及系统常量。
          支持优先从当前目录的 .env 文件或系统环境变量中加载配置。
可移植性: 零外部重型依赖，仅使用 Python 内置库（os, pathlib），方便在任何环境迁移。
==============================================================================
"""

import os
from pathlib import Path

# ==============================================================================
# 1. 基础路径配置
# ==============================================================================

# 项目根目录路径（以当前 config.py 所在目录为准）
PROJECT_ROOT = Path(__file__).resolve().parent

# 数据根目录 (默认位于 project_root/data)
DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", PROJECT_ROOT / "data"))

# 物理分类存储目录（各类原始文件分门别类归档的位置）
STORAGE_DIR = DATA_DIR / "storage"

# 本地数据库目录（包含 SQLite 元数据及向量检索缓存）
DB_DIR = DATA_DIR / "db"

# 生成物导出目录（存放 Agent 逆向生成的新 docx / pptx）
OUTPUT_DIR = DATA_DIR / "output"

# 提示词模板目录与自定义 PPT 提示词文件路径 (可由用户随时自由编辑调整)
PROMPTS_DIR = PROJECT_ROOT / "prompts"
PPT_PROMPT_TEMPLATE_PATH = PROMPTS_DIR / "ppt_prompt.txt"

# 确保核心工作目录在初始化时即存在
for directory in [DATA_DIR, STORAGE_DIR, DB_DIR, OUTPUT_DIR, PROMPTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# 2. 简单的 .env 加载器 (避免引入额外的 python-dotenv 库，增强可移植性)
# ==============================================================================

def load_env_file(dotenv_path: Path = PROJECT_ROOT / ".env") -> None:
    """
    轻量级从 .env 文件中加载环境变量到 os.environ
    如果 .env 文件不存在则跳过，不阻断运行
    """
    if not dotenv_path.is_file():
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 忽略空行和注释行
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            # 去除可能包含的引号
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if key not in os.environ:
                os.environ[key] = val

# 执行环境配置加载
load_env_file()


# ==============================================================================
# 3. 大语言模型配置 (LLM Configuration)
# ==============================================================================

# 默认选用 Provider: "deepseek"（后续可扩展为 "openai", "claude", "local" 等）
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek")

# DeepSeek 核心参数
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 大模型超时与重试参数（单位：秒）
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))


# ==============================================================================
# 4. 业务规则与分类定义
# ==============================================================================

# 默认预设的文档分类类别（当大模型分类时作为先验推荐，但允许模型扩展）
DEFAULT_CATEGORIES = [
    "需求与产品设计",
    "技术架构与方案",
    "会议纪要与周报",
    "总结与汇报演示",
    "学习笔记与参考",
    "未分类杂项"
]

# 问答召回数量设置 (Top-K)
DEFAULT_RETRIEVAL_TOP_K = 4

# SQLite 数据库文件绝对路径
SQLITE_DB_PATH = DB_DIR / "agent_metadata.db"


# ==============================================================================
# 5. 维测日志与可观测性配置 (Observability & Trace Logger)
# ==============================================================================

# 是否开启 Harness ⇄ LLM 深度维测轨迹记录 (默认 False)
AGENT_DEBUG = os.getenv("AGENT_DEBUG", "false").lower() in ("true", "1", "yes")

# 维测日志输出文件路径 (默认输出到项目根目录下的 agent_debug.txt)
AGENT_DEBUG_FILE = Path(os.getenv("AGENT_DEBUG_FILE", PROJECT_ROOT / "agent_debug.txt"))

# 单个日志文件上限大小 (单位: MB，默认 10MB)
AGENT_DEBUG_MAX_MB = int(os.getenv("AGENT_DEBUG_MAX_MB", "10"))

# 滚动日志历史备份最大保留份数 (默认保留 2 份: agent_debug.txt.1, agent_debug.txt.2)
AGENT_DEBUG_BACKUP_COUNT = int(os.getenv("AGENT_DEBUG_BACKUP_COUNT", "2"))
