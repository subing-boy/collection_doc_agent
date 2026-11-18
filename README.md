# 个人文档管家 Agent (Personal Doc & PPT Agent)

一个专为个人与团队知识沉淀打造的智能文档助手。具备 **“多格式切片归档 ➔ 带出处精准问答 ➔ 逆向综合生成 Doc/PPT”** 的全生命周期能力。

---

## 一、核心特性与交互模式

1. **模式一：文件输入与分类存储（Ingestion）**
   - 接收输入的 Word (`.docx`) 与 PowerPoint (`.pptx`) 文件。
   - **PPT 精密切片**：以 `1 Slide = 1 Chunk` 进行原子切片，提取标题、正文文本框、数据表格以及演讲者备注（Notes）。
   - **Word 结构切片**：依据标题层级（Heading 1/2/3）切片，自动记录面包屑路径（如 `1. 核心架构 > 1.2 数据流转`）。
   - **智能分类流转**：由 DeepSeek 提炼主题，物理归档至 `data/storage/<分类>/` 目录，并在 SQLite 与本地向量引擎中持久化元数据。

2. **模式二：带出处溯源问答与逆向生成（Q&A & Generation）**
   - **严格出处溯源**：系统内置强约束 Prompt，回答中凡涉及资料事实均强制附带标签：`[出处: 文档名, 坐标]`（如：`[出处: 架构设计.pptx, 第2页 (核心设计)]`）。资料未提及则明确告知，严禁模型幻觉。
   - **逆向导出 Word (`.docx`)**：综合知识库资料，自动组织段落、要点列表与表格，导出带标准样式的 Word 报表。
   - **逆向渲染 16:9 商业 PPT (`.pptx`)**：由大模型规划结构化卡片阵列，自动渲染出符合现代 16:9 宽屏版式的幻灯片文件。

3. **高阶预留骨架（首版预留插槽，方便后续人工补充与 Review）**
   - **记忆压缩 (`core/memory_manager.py`)**：跟踪多轮会话轮次与 Token 开销，预留超过阈值时触发异步摘要降维的开发规范。
   - **问题重写与重试 (`core/query_optimizer.py`)**：监控初次检索相似度得分与大模型未命中反馈，预留基于大模型的问题同义词扩展与二次检索逻辑。

---

## 二、项目目录结构与模块说明

```text
collection_doc_agent/
├── config.py                 # 全局配置管理（大模型端点、默认分类、存储路径等）
├── requirements.txt          # Python 依赖清单
├── .env.example              # 环境变量配置模板（复制为 .env 使用）
├── main.py                   # 命令行与交互式 Shell 统一入口
│
├── core/                     # 核心业务调度层
│   ├── agent_core.py         # 核心编排引擎（Agent 大脑，串联上传、问答、生成流程）
│   ├── classifier.py         # 智能分类器（LLM 主题分类与物理文件搬运）
│   ├── memory_manager.py     # 记忆压缩管理器（多轮对话跟踪与降维接口）
│   └── query_optimizer.py    # 问题改写与重试优化器（未命中拦截与重试接口）
│
├── parsers/                  # Office 文档精密解析层
│   ├── base_parser.py        # 解析抽象基类与 DocumentChunk 规范
│   ├── pptx_parser.py        # PPTX 幻灯片逐页解析（提取页码、表格、演讲者备注）
│   └── docx_parser.py        # DOCX 文档章节解析（维护标题面包屑与表格）
│
├── storage/                  # 数据持久化与向量索引层
│   ├── metadata_db.py        # 基于 SQLite 的文档元数据与切片关系存储
│   └── vector_store.py       # 嵌入式轻量级向量检索引擎（支持余弦相似度与出处透传）
│
├── llm/                      # 大模型网关层 (支持无缝扩展多模型)
│   ├── base_provider.py      # LLM 统一接口抽象基类
│   ├── deepseek_provider.py  # DeepSeek API 客户端封装（基于 requests，含自动重试与 JSON 模式）
│   └── embeddings.py         # 纯 Python 零依赖稠密向量引擎（跨任何平台与 Python 版本）
│
├── generators/               # 逆向生成引擎层
│   ├── doc_generator.py      # Word 报告逆向生成器
│   └── ppt_generator.py      # 16:9 现代商业版式 PPT 逆向渲染器
│
├── data/                     # 数据资产根目录 (运行时自动创建)
│   ├── storage/              # 物理分类存储目录（按类别划分文件夹）
│   ├── db/                   # SQLite 数据库与向量缓存
│   └── output/               # 逆向生成导出的 docx / pptx 成果物
│
└── tests/
    └── test_skeleton.py      # 全链路自动化端到端测试套件
```

---

## 三、快速开始

### 1. 安装核心依赖
系统采用零重型 C 依赖设计，可在任意标准 Python 环境（包括 Python 3.10 ~ 3.14）秒级运行：
```bash
pip install -r requirements.txt
```

### 2. 配置 DeepSeek API 密钥
复制环境变量模板并填入您的 DeepSeek API Key：
```bash
cp .env.example .env
```
编辑 `.env`：
```ini
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```
*(注：即使暂未填入 API Key，系统也可以正常启动，并能自动降级运行离线解析、分类、向量检索与自测单测)*

### 3. 运行全链路端到端自测
```bash
python3 tests/test_skeleton.py
```

### 4. 启动交互式 Agent
```bash
python3 main.py
```
进入交互 Shell 后：
- **拖入/输入文件路径**（如 `path/to/demo.pptx` 或 `doc.docx`）➔ 自动完成切片、语义分类并归档！
- **直接提问**（如 `核心架构设计是什么？`）➔ 检索并输出带精准出处（文件名、页码）的回答！
- **生成文档**：输入 `make-doc <主题>` ➔ 自动综合库内资料导出 `.docx`。
- **生成演示**：输入 `make-ppt <主题>` ➔ 自动规划并导出 16:9 现代版式 `.pptx`。
- **查看清单**：输入 `list` ➔ 查看当前已归档文件及分类。

### 5. 命令行单行指令调用
```bash
# 上传归档
python3 main.py ingest /path/to/document.docx

# 溯源问答
python3 main.py ask "系统的存储方案是如何设计的？"

# 查看文档列表
python3 main.py list

# 生成报告
python3 main.py make-doc "系统架构与技术选型总结"

# 生成 PPT
python3 main.py make-ppt "年度核心技术成果汇报"
```

---

## 四、代码 Review 与后续扩展指南

针对后续由人工填充的两个核心高级特性：
1. **记忆压缩 (`core/memory_manager.py` 中的 `compress_history` 方法)**：
   - 当前已搭建好会话跟踪器与滑动窗口。
   - 查看该方法中的 `TODO 1 ~ TODO 5` 提示，只需接入预留的 Prompt 并调用 `llm_provider` 即可实现自动长会话摘要降维。
2. **问题重写与重试 (`core/query_optimizer.py` 中的 `rewrite_query` 方法)**：
   - 当前已搭建好未命中置信度阈值与“未找到”指示词拦截逻辑。
   - 查看该方法中的 `TODO 1 ~ TODO 4` 提示，可直接补充同义词扩展和长尾问题改写逻辑。
