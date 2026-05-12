# DEBUG 记录

记录运行过程中的报错、原因与修复经验，避免重复踩坑。

---

## 运行测试时的注意事项

- 首次启动前需设置 `ANTHROPIC_API_KEY` 环境变量（RAG 对话功能依赖）
- 首次启动前需运行 `python backend/knowledge/ingest.py` 构建向量知识库
- 美股数据获取需设置代理：`set -x all_proxy http://127.0.0.1:7897`（fish shell）

---

（以下将在运行测试过程中持续更新）
