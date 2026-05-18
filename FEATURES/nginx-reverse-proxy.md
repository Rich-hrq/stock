# Feature: Nginx 反向代理部署

## 需求背景

为了将服务部署到服务器供外网访问，在 uvicorn 前加一层 Nginx 反向代理，同时提供安全访问外部新闻原文的能力。

## 需求总结

| 项目 | 决策 |
|------|------|
| 代理层 | Nginx（反向代理 uvicorn） |
| uvicorn 绑定 | 127.0.0.1:8000（不对外暴露） |
| 配置方式 | 站点配置 + 一键部署脚本 |
| 应用内代理 | Guardian 原文反向代理（base 标签注入 + 域名白名单） |

---

## 功能边界

### 做什么
- Nginx 反向代理到本地 uvicorn 进程
- 提供一键部署脚本（setup_nginx.sh）
- 提供详细的配置原理指南（GUIDE.md）
- 应用内代理：安全访问 Guardian 新闻原文，注入 base 标签修复相对路径

### 不做什么
- 不处理 HTTPS（用户自行配置 SSL 证书）
- 不提供 Docker 部署方案
- 不做负载均衡

---

## 核心设计

### 外部访问流

```
用户 → http://<服务器IP>
  → Nginx (port 80) → proxy_pass http://127.0.0.1:8000
  → uvicorn → FastAPI
```

### 应用内代理

```
用户点击新闻链接 → GET /api/proxy?url=<原文URL>
  → services/proxy.py: httpx 获取原文
  → 注入 <base href="原文base URL"> 修复 CSS/图片相对路径
  → 域名白名单校验
  → 返回完整 HTML
```

---

## 边界条件

- Nginx 必须与服务端在同一台机器
- 应用内代理仅对白名单域名生效
- 无 HTTPS 时不建议暴露到公网

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `nginx_config/nginx-stock.conf` | 新增 |
| `nginx_config/setup_nginx.sh` | 新增 |
| `nginx_config/GUIDE.md` | 新增 |
| `backend/routers/proxy.py` | 新增 |
| `backend/services/proxy.py` | 新增 |

---

## 风险与注意事项

- 生产环境应配置 HTTPS + 真实域名
- uvicorn 应仅监听 127.0.0.1，防止直接暴露到外网
- nginx_conf 中需替换 `<your-server-ip>` 为实际 IP
- 反向代理时 uvicorn 未重启可能导致 merge 后 404（记录在 DEBUG.md）
