# Feature: RAG 智能问答系统（v1→v2→v3）

## 需求背景

基于《海龟交易法则》原书 PDF 构建知识问答系统，用户能用自然语言提问交易策略相关问题，系统从书中检索相关内容后生成精准回答。

## 需求总结

| 项目 | 决策 |
|------|------|
| 知识来源 | 《海龟交易法则》PDF（约256页） |
| 向量数据库 | ChromaDB（本地持久化） |
| 嵌入模型 | paraphrase-multilingual-MiniLM-L12-v2 |
| LLM 框架 | LangGraph（状态图编排） |
| LLM 兼容 | Claude / DeepSeek 等 Anthropic 兼容 API |
| 默认版本 | v3（智能评估 + 选择性扩展 + 多查询融合检索） |

---

## 功能边界

### 做什么
- PDF → 文本切片 → 向量化 → ChromaDB 存储（一次性 ingest）
- 用户提问 → RAG 检索 → LLM 生成（严格基于原文）
- 三版本共存，可对比测试
- 返回来源引用（页码、文本块）

### 不做什么
- 不支持非海龟交易法则相关的通用问答
- 不实时更新知识库（PDF 固定）
- 不支持多语言（仅中文提问，中文回答）

---

## 核心设计

### v1: retrieve → generate
- 最简流水线：直接用问题检索 ChromaDB，Top-K 结果注入 context

### v2: rewrite → retrieve → judge → 条件路由
- 查询改写：专业术语同义转述
- 相关性判断：L2 距离阈值 10.0 过滤
- 条件路由：相关→生成；不相关→提示用户

### v3: evaluate → 选择性扩展 → 多查询融合 → generate
- evaluate_node: 判断问题是否已精确
- expand_node: 不精确时生成 2-3 个专业转述
- retrieve_node: 多查询分别检索，合并去重，按距离排序，取 top-4
- generate_node: 组装 Prompt → LLM 生成

### 检索参数
- Top-K: 4 个最相关文本块
- 距离度量：L2 距离（余弦相似度在 ChromaDB 中等价）

---

## 边界条件

- 知识库为空时返回提示
- LLM 不可用时返回错误提示
- 问题过于宽泛时 v3 自动扩展，v1/v2 检索质量下降

---

## 实现计划

1. 搭建 LangChain + ChromaDB 知识库基础架构
2. 实现 PDF 文本提取 + 切片 + 向量化（ingest.py）
3. 实现 RAG v1（基础检索+生成）
4. 实现 RAG v2（查询改写 + 相关性判断）
5. 实现 RAG v3（智能评估 + 多查询融合）
6. 编写三版本对比测试脚本（test_rag.py）
7. 前端聊天对话框 + 对话历史
8. 兼容 DeepSeek Anthropic 兼容 API

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/services/rag.py` | 新增（v1） |
| `backend/services/rag_v2.py` | 新增 |
| `backend/services/rag_v3.py` | 新增 |
| `backend/routers/chat.py` | 新增 |
| `backend/knowledge/ingest.py` | 新增 |
| `backend/knowledge/test_rag.py` | 新增 |
| `frontend/js/chat.js` | 新增 |
| `backend/schemas.py` | 新增 ChatRequest/ChatResponse |

---

## 风险与注意事项

- HuggingFace 模型下载需代理（国内环境）
- LangChain 版本升级可能导致导入路径变更（如 text_splitter 迁移）
- 不同 LLM (Claude vs DeepSeek) 格式返回可能不同，需兼容 content blocks 列表格式
- v3 口语化更好但存在过度扩展问题，需持续校准
