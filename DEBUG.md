# DEBUG 记录

记录运行过程中的报错、原因与修复经验，避免重复踩坑。

---

## 运行测试时的注意事项

- 首次启动前需设置 `ANTHROPIC_API_KEY` 环境变量（RAG 对话功能依赖）
- 首次启动前需运行 `python backend/knowledge/ingest.py` 构建向量知识库
- 美股数据获取需设置代理：`set -x all_proxy http://127.0.0.1:7897`（fish shell）

---

## 首次启动出现端口占用

**现象**：uvicorn 启动后 curl 返回 `Connection refused`

**原因**：多次后台启动 uvicorn 导致端口 8000 残留

**解决**：`lsof -ti:8000 | xargs kill -9` 清理端口后重启

---

## 聊天 API 需要 ANTHROPIC_API_KEY

**现象**：`POST /api/chat` 返回 500:"Could not resolve authentication method"

**原因**：Anthropic SDK 未检测到有效的 API Key

**解决**：启动前设置环境变量：
```fish
set -x ANTHROPIC_API_KEY sk-ant-xxx   # fish
```
或
```bash
export ANTHROPIC_API_KEY=sk-ant-xxx   # bash
```
