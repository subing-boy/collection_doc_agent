# 个人文档管家 Agent (Personal Doc & PPT Agent)

一个专为个人与团队知识沉淀打造的智能文档助手。具备 **“多格式切片归档 ➔ 带出处精准问答 ➔ 逆向综合生成 Doc/PPT”** 的全生命周期能力，以 DeepSeek API 为大模型后端，基于纯 Python 零编译依赖架构构建。

---

## 一、核心特性与交互模式

1. **模式一：多格式输入与分类存储（Ingestion & Dedup）**
   - **六大格式深度支持**：原生支持 Word (`.docx`)、PowerPoint (`.pptx`)、Excel (`.xlsx`)、Outlook 邮件 (`.msg`)、Markdown (`.md`) 与纯文本 (`.txt`)。
   - **四象限防重与版本流转**：基于文件内容 SHA256 哈希与原始文件名秒级防重。同名同内容秒级拦截；同名改动就地升级并级联清除旧切片；改名同内容自动追加别名映射。
   - **智能分类归档**：由大模型分析文档前瞻特征，物理分流归档至 `data/storage/<分类>/` 目录，并在 SQLite 与本地向量引擎中持久化元数据。

2. **模式二：带出处精准溯源问答与 Agent Loop（Q&A & Agent Loop）**
   - **严格出处溯源**：系统内置强约束红线，回答中凡涉及事实、参数、数据均强制附带标签：`[出处: 文档名, 坐标]`（如：`[出处: 架构设计.md, 1.2 核心通道]` 或 `[出处: 预算表.xlsx, 工作表: 成本明细, 第2-26行]`）。
   - **双路混合检索 (Hybrid Search)**：50% 语义向量余弦相似度 + 50% 概念交集加权。引入复合短语防饱和、罕见专业术语特异性加权与多概念交集奖励（`Intersection Bonus`），彻底避免长句通用词淹没核心生僻术语。
   - **4 轮 Agent Loop 自主纠错与深度筛查**：当下发复杂提问且初次检索未覆盖核心实体时，Agent 不会单轮放弃，而是自主唤醒工具箱：
     - `deep_keyword_grep`：全库穿透检索指定专有名词；
     - `expand_adjacent_chunks`：自动抓取目标章节前后连续上下文（如 Phase 1 自动联动 Phase 2）；
     - 硬编码 4 轮上限（`MAX_AGENT_LOOPS = 4`）与工具调用去重锁，**物理级杜绝死循环卡死**。

3. **模式三：快慢双车道意图驱动与逆向生成（Dual-Lane Intent & Generation）**
   - **车道 1（本地快车道 - 0ms）**：拖拽文件入库、控制命令（`list`, `exit`）、显式命令行前缀（`make-doc`, `make-ppt`）直接本地秒级直达，0 Token 开销。
   - **车道 2（大模型语义慢车道）**：复杂口语长句（如 *“制作一个live mode vad的具体需求方案 放在D:\download路径下”*），由语义路由器识别意图并自动提取主题与目标保存路径（支持 Windows 盘符 `D:\...` 自动归一化）。
   - **可配置 Prompt 模板热加载**：根目录下设立 `prompts/ppt_prompt.txt` 与 `prompts/doc_prompt.txt`，用户随时编辑修改演示文稿与技术方案的设计风格与排版结构，即改即热生效。

4. **模式四：透明化维测轨迹追踪（Observability & Trace Logger）**
   - 支持在 `.env` 中通过 `AGENT_DEBUG=true|false` 控制维测开关（关闭时 0 额外耗时与 0 磁盘 I/O）。
   - 开启后在根目录下生成直观易读的单个文本日志 **`agent_debug.txt`**，完整记录：System Prompt、历史对话、可用工具、实际调用的工具与检索得分、发送给 LLM 的 Payload、AI 原始回答以及端到端耗时。
   - 内置 **10MB 自动轮转与备份淘汰机制**（默认最多保留 2 份备份：`.1` 与 `.2`），并在 `.gitignore` 中受保护，彻底杜绝日志无限膨胀撑爆磁盘或误传泄密。

---

## 二、知识库存储资产边界（可以存什么 vs 不可以存什么）

为了保证知识库向量空间的纯净度与检索出处的高确定性，系统建立了清晰的存储能力矩阵：

### 1. ✔ 原生深度支持格式清单（可以直接存入）

| 文件类型 | 推荐后缀 | 专有精密切片策略 | 精准出处定位坐标示例 | 典型适用业务场景 |
| :--- | :--- | :--- | :--- | :--- |
| **Word 文档** | `.docx` | 依据 Heading 1/2/3 标题层级切片，维护章节面包屑路径 | `[出处: 规范.docx, 1. 核心架构 > 1.2 数据流]` | 技术方案、协议规范、业务说明书 |
| **PowerPoint 演示** | `.pptx` | 1 Slide = 1 Chunk 原子切片，深度挖掘正文、表格与**演讲者备注** | `[出处: 汇报.pptx, 第3页 (系统拓扑)]` | 架构全景汇报、商业提案、项目周报 |
| **Excel 电子表格** | `.xlsx`, `.xlsm` | 按工作表（Sheet）遍历，以 25 行为块维护表头生成 Markdown 自解释表格 | `[出处: 预算.xlsx, 工作表: 研发成本, 第2-26行]` | 财务预算、测试用例表、接口参数矩阵 |
| **Outlook 邮件** | `.msg` | 结构化抽取主题、发件人、收件人、时间，邮件头置顶作为切片前置上下文 | `[出处: 终审决议.msg, 发件人: 王总, 时间: 2026-11-18]` | 关键技术决策邮件链、立项批复往来 |
| **Markdown 文档** | `.md`, `.markdown` | 递归解析 `#` 标题层级（H1~H4），自建栈结构维护章节面包屑路径 | `[出处: 设备设计.md, 8. VAD功能 > 8.2 Phase 2]` | 开发指南、架构方案、开源项目文档 |
| **纯文本文件** | `.txt` | 基于换行与字数边界自适应语义段落分块 | `[出处: 会议纪要.txt, 第2部分]` | 快速临时记录、纯文本笔记、配置摘录 |

---

### 2. ❌ 明确不支持/禁止直接入库格式清单（及底层原因）

| 不支持的文件类别 | 常见扩展名 | 不支持原因剖析 | 替代操作与转换建议 |
| :--- | :--- | :--- | :--- |
| **纯二进制与可执行程序** | `.exe`, `.dll`, `.so`, `.bin`, `.hex` | **无文本语义**：二进制机器码注入向量库会产生巨大的向量噪声，彻底污染文本检索空间。 | **禁止入库**。若需沉淀代码说明，请编写并存入 `.md` 说明文档。 |
| **压缩归档包** | `.zip`, `.rar`, `.7z`, `.tar.gz` | **归档容器而非单一文档**：压缩包直接读取为十六进制乱码，无法维持目录内各类文件的独立出处。 | **解压后再存**：在本地将压缩包解压，把里面的 `.docx`/`.pptx`/`.md` 单独拖入入库。 |
| **音视频多媒体文件** | `.mp4`, `.mp3`, `.wav`, `.avi`, `.mkv` | **缺少多模态感知模型**：当前架构专注于轻量高移植性，未引入重型本地 ASR 语音模型或视频抽帧引擎。 | **文字转录后存入**：使用语音转文字工具将会议录音转录为 `.txt` 或 `.docx` 会议纪要后存入。 |
| **纯图片与扫描件** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp` | **缺少 OCR 识别引擎**：未挂载重型 Tesseract / PaddleOCR 库，避免破坏零 C 编译依赖的跨平台轻量性。 | **OCR 提取后再存**：使用截图 OCR 工具复制出文本，整理为 `.md` 或 `.docx` 后存入知识库。 |
| **微软旧版二进制 Office** | `.doc`, `.xls`, `.ppt` | **老旧复合二进制封装**：微软 97-2003 的专有 OLE2 二进制格式，解析极其笨重且易发生结构损坏。 | **另存为现代格式**：在 Office/WPS 中打开文件，点击“另存为”现代格式（`.docx`/`.xlsx`/`.pptx`）后入库。 |
| **PDF 印刷排版文档** | `.pdf` | **页面流非线性**：为保证零外部编译库的轻量运行，首版暂未内置 PDF 库（系统已预留 `PDFParser` 抽象插槽）。 | **演进规划中**：后续版本将挂载轻量纯 Python 解析器；当前可另存为 Word 或 Markdown 后存入。 |

---

## 三、项目目录结构与模块说明

```text
collection_doc_agent/
├── config.py                 # 全局配置管理（大模型端点、默认分类、存储路径、提示词路径等）
├── requirements.txt          # 纯 Python 依赖清单（无重型 C++ 编译依赖）
├── .env.example              # 环境变量配置模板（复制为 .env 使用）
├── agent_debug.txt           # 维测追踪日志（由 AGENT_DEBUG 控制，10MB 自动轮转，被 gitignore 保护）
├── main.py                   # 命令行与交互式 Shell 统一入口（集成快慢双车道意图分流）
│
├── prompts/                  # 独立可配置的提示词模板目录 (用户可随时直接编辑修改)
│   ├── ppt_prompt.txt        # 16:9 商业 PPT 规划生成 Prompt 模板 (热加载)
│   └── doc_prompt.txt        # Word 技术方案与需求文档生成 Prompt 模板 (热加载)
│
├── core/                     # 智能体核心大脑与调度层
│   ├── agent_core.py         # 核心编排引擎（4轮 Agent Loop、混合检索组装、双向打点）
│   ├── intent_router.py      # 快慢双车道意图路由器（规则快车道 + 大模型语义慢车道）
│   ├── classifier.py         # 智能分类器（双轨制语义决策与物理磁盘迁移）
│   ├── memory_manager.py     # 记忆管理器（多轮对话跟踪与上下文滑动窗口）
│   ├── query_optimizer.py    # 提问优化与质量门禁（实体覆盖度核验与未命中指示词识别）
│   └── trace_logger.py       # 系统级维测日志引擎（基于 RotatingFileHandler 实现 10MB 自动轮转）
│
├── parsers/                  # 多格式结构化解析驱动层 (抽象工厂模式)
│   ├── base_parser.py        # 解析抽象基类与 DocumentChunk / ParsedDocument 数据契约
│   ├── pptx_parser.py        # PPTX 逐页幻灯片解析（提取页码、文本、表格与演讲者备注）
│   ├── docx_parser.py        # DOCX 章节解析（维护 Heading 面包屑与表格数据）
│   ├── excel_parser.py       # Excel 工作簿表格解析（多 Sheet 遍历与带表头自解释矩阵切片）
│   ├── msg_parser.py         # Outlook 邮件解析（通信头置顶与正文段落切片）
│   └── markdown_parser.py    # Markdown 与纯文本解析（递归 # 标题层级与面包屑维护）
│
├── storage/                  # 数据持久化与向量索引层
│   ├── metadata_db.py        # 基于 SQLite 的元数据与切片关系数据库（含穿透筛查与章节连续扩展工具）
│   └── vector_store.py       # 嵌入式混合向量引擎（短语防饱和、概念覆盖率、多概念交集奖励 +0.35）
│
├── llm/                      # 大模型网关层
│   ├── base_provider.py      # LLM 统一接口抽象基类
│   ├── deepseek_provider.py  # DeepSeek API 网关（基于 requests，含重试机制与 JSON 模式）
│   └── embeddings.py         # 纯 Python 零依赖稠密特征向量计算工具 (128维 N-gram 哈希)
│
├── generators/               # 逆向生成引擎层 (支持自定义目录落盘)
│   ├── doc_generator.py      # Word 报告与方案逆向生成器
│   └── ppt_generator.py      # 16:9 现代商业版式 PPT 逆向渲染器
│
├── data/                     # 数据资产根目录 (运行时自动创建，代码与数据物理隔离)
│   ├── storage/              # 物理分类存储目录（按类别划分层级文件夹）
│   ├── db/                   # SQLite 数据库文件 (agent_metadata.db)
│   └── output/               # 逆向生成导出的默认成果物目录
│
└── tests/
    └── test_skeleton.py      # 全链路自动化端到端测试套件 (沙箱隔离运行并在完成后强制彻底销毁)
```

---

## 四、快速开始

### 1. 安装核心依赖
系统采用纯 Python 设计，在任意环境（包括 Linux, Windows, WSL 及 Python 3.10 ~ 3.14）均可秒装运行：
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
复制模板生成 `.env` 文件：
```bash
cp .env.example .env
```
编辑 `.env`：
```ini
# DeepSeek 大模型配置
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 维测追踪总开关 (按需开启，为 true 时输出 agent_debug.txt，默认关闭 0 磁盘 I/O)
AGENT_DEBUG=true
```

### 3. 运行全链路端到端自测试套件
```bash
python3 tests/test_skeleton.py
```
*(自测套件运行在沙箱隔离临时目录中，100% 覆盖全部核心特性并在执行完毕后强制彻底销毁，保证 data/ 生产数据绝对纯净)*

### 4. 启动交互式文档管家
```bash
python3 main.py
```

进入交互终端后支持以下无拘束操作：
* **存文档**：直接输入或拖入文件路径（如 `D:\协议文档\AIW.docx`，或漏输后缀 `D:\download\Live_Mode` 自动探测补齐），秒级完成四象限防重、分类与入库；
* **查知识**：直接用自然语言提问（如 `live mode 中 vad 具体实现请写出一个具体的需求文档`），系统多概念交集匹配 + 4 轮 Agent Loop 深度自愈，输出带精准出处（如 `[出处: 文档.md, 8.2 Phase 2]`）的回答；
* **做方案/Word**：输入自然语言长句（如 `制作一个live mode vad的具体需求方案 放在D:\download路径下`），快慢双车道意图分流，读取 `prompts/doc_prompt.txt` 并直接导出 `.docx`；
* **做演示/PPT**：输入长句（如 `总结一下live mode device + ca + ai 的主要内容包括流程 生成ppt到D:\download路径下`），自动提纯主题并导出 16:9 宽屏 `.pptx`；
* **查资产**：输入 `list` 查看已归档文档清单及分类统计；
* **退出**：输入 `exit` 或 `quit` 退出系统。
