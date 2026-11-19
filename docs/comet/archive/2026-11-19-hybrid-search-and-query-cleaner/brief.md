# 目标

在知识检索链路中引入“提问口语噪音清洗”与“关键词精确匹配 + 向量相似度双路混合检索（Hybrid Search）”机制：
1. 提问提纯（Query Preprocessing）：提取用户 Query 中的英文专有名词与核心术语，过滤无实质检索意义的口语化中英文停用词与元语言（如“在知识库中寻找”、“帮我查一下”、“相关的内容”、“有哪些”等），防止噪音字符主导向量空间；
2. 关键词精准路（Lexical Route）：在 SQLite 中根据提取的核心关键词进行模糊/词根检索，对包含核心专有名词的切片赋予精确命中加权分；
3. 语义向量路（Dense Vector Route）：基于提纯后的 Query 计算向量与余弦相似度；
4. 混合重排融合（Hybrid Fusion）：将关键词精准命中分与语义向量分加权融合排序，确保长句口语提问也能精准将专有名词所在切片推到 Top-1；
5. 彻底解决类似 `知识库中寻找和ai chat相关的内容` 无法召回 `5.21 AI Chat(0x21)` 协议切片的漏搜问题。

# 范围

## 目录结构

### 修改
- `storage/metadata_db.py`: 新增 `search_chunks_by_keywords(keywords)` 接口，支持按关键词统计切片词频与命中加权分。
- `storage/vector_store.py`: 升级 `search()` 支持双路混合检索，将关键词命中得分与向量余弦相似度进行无缝融合重排。
- `core/agent_core.py`: 引入 `clean_query_and_extract_keywords()` 纯本地零开销提纯算法，在 `ask()` 中调用混合检索。
- `tests/test_skeleton.py`: 新增口语长句混合检索针对性测试用例。

### 明确不建
- 不引入外部重型搜索引擎守护进程（Elasticsearch / Meilisearch），保持 SQLite + 纯 Python 的极简可移植架构。

# 非目标

- 不破坏已有的 `ingest_document()`、`generate_new_doc()`、`generate_new_ppt()` 等既有业务接口。
- 清洗与提取算法必须纯本地毫秒级完成，严禁调用 LLM 产生额外延迟与 Token 费用。

# 验收示例

- 输入长句口语 `知识库中寻找和ai chat相关的内容`，能精准提纯核心词并召回包含 `5.21 AI Chat(0x21)` 的切片作为 Top 1 结果。
- 输入英文专有名词与口语结合的长句（如 `帮我查一下L2CAP COC协议的具体数据分包逻辑`），能准确命中 `3.2 L2CAP COC Profile` 相关切片。
- 纯自然语言语义问题（不含生僻专有名词）依然保持高质量向量语义匹配。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动清理无残留。
