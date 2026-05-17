# Nginx 反向代理配置指南

以本项目（美股指数分析 FastAPI 后端）为例，讲解如何使用 Nginx 进行反向代理，使远程主机可以通过 IP 访问服务。

---

## 一、什么是反向代理

### 正向代理 vs 反向代理

```
正向代理（Forward Proxy）：客户端 → 代理服务器 → 目标服务器
       你               已知            未知（Google/Youtube等）
   —— 代理替你访问外部，服务端不知道真正的客户端是谁

反向代理（Reverse Proxy）：客户端 → 代理服务器 → 内部服务器
     外部用户         反向代理            内网应用
   —— 代理替你接客，客户端不知道真正的服务端是谁
```

**本项目场景**：
```
远程浏览器 → http://10.208.141.191:80 → nginx → http://127.0.0.1:8000 (uvicorn)
                                          ↑
                                     反向代理层
```

### 为什么需要反向代理

| 能力 | 说明 |
|------|------|
| 隐藏后端 | 外部只知道 nginx（80/443 端口），uvicorn 只监听本地 127.0.0.1 |
| 静/动分离 | nginx 直接 serve 静态文件（CSS/JS），不用经过 Python |
| HTTPS 终结 | SSL 证书配置在 nginx，后端无需处理加密 |
| 负载均衡 | 多个 uvicorn worker 之间分发请求 |
| 限流/缓存 | 防止滥用，缓存常用响应 |
| Gzip 压缩 | 压缩响应体，节省带宽 |

---

## 二、Nginx 是什么

Nginx 是一个高性能 HTTP 服务器，诞生于 2004 年（作者 Igor Sysoev），专为解决 C10K 问题（单机同时处理 10000+ 连接）而设计。

### 核心特性

- **事件驱动 + 异步非阻塞**：单 master 进程 + 多个 worker 进程，每个 worker 以事件循环方式处理数千连接，不像 Apache 为每个连接 fork 一个线程
- **内存占用低**：静态文件服务场景下，万级并发仅占用几十 MB 内存
- **热重载**：`nginx -s reload` 平滑更新配置，不中断现有连接
- **反向代理**：内置 `proxy_pass` 指令，支持 HTTP/1.1、WebSocket、FastCGI

### Nginx 配置文件结构

```
/etc/nginx/
├── nginx.conf              ← 主配置（全局设置 + include 子配置）
├── sites-available/        ← 所有可用的站点配置（仓库）
│   └── stock               ← 我们创建的站点
├── sites-enabled/          ← 已启用的站点（symlink 到 sites-available）
│   └── stock -> ../sites-available/stock
└── modules-enabled/        ← 加载的模块
```

`nginx.conf` 中包含 `include /etc/nginx/sites-enabled/*;`，所以放到 `sites-enabled/` 的配置文件都会被加载。

---

## 三、配置步骤详解

### 步骤 1：安装 Nginx

```bash
sudo apt update
sudo apt install nginx -y
sudo systemctl start nginx
sudo systemctl enable nginx     # 开机自启
```

安装后验证：
```bash
nginx -v                        # 查看版本
sudo systemctl status nginx     # 查看运行状态
```

此时访问 `http://<IP>` 会看到 Nginx 默认欢迎页。

### 步骤 2：编写站点配置文件

创建 `/etc/nginx/sites-available/stock`：

```nginx
server {
    listen 80;
    server_name 10.208.141.191;

    access_log /var/log/nginx/stock-access.log;
    error_log  /var/log/nginx/stock-error.log;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**逐行解释**：

| 指令 | 含义 |
|------|------|
| `server { }` | 定义一个虚拟主机（站点）。一个 nginx 实例可以跑多个 server |
| `listen 80` | 监听 80 端口（HTTP 默认端口） |
| `server_name 10.208.141.191` | 匹配 Host 头为该 IP 的请求。用于区分同一端口上的多个站点 |
| `access_log / error_log` | 分别记录正常访问和错误日志，按站点隔离方便排查 |
| `location / { }` | 匹配所有以 `/` 开头的 URL。可写多个 location 做精细化路由 |
| `proxy_pass http://127.0.0.1:8000` | **核心指令**：将匹配的请求转发到 `127.0.0.1:8000`（uvicorn） |
| `proxy_set_header Host $host` | 透传客户端请求的原始 Host 头，否则后端看到的是 `127.0.0.1:8000` |
| `proxy_set_header X-Real-IP $remote_addr` | 把真实客户端 IP 传给后端（否则后端日志全显示 127.0.0.1） |
| `proxy_set_header X-Forwarded-For` | 代理链追踪（如果前面还有 CDN/负载均衡） |
| `proxy_set_header X-Forwarded-Proto` | 告知后端原始请求是 http 还是 https |

### 步骤 3：启用站点

```bash
# 方式一：手动操作
sudo cp nginx_config/nginx-stock.conf /etc/nginx/sites-available/stock
sudo rm /etc/nginx/sites-enabled/default   # 去掉默认欢迎页
sudo ln -s /etc/nginx/sites-available/stock /etc/nginx/sites-enabled/stock

# 方式二：执行本项目提供的脚本
sudo bash nginx_config/setup_nginx.sh
```

`site-enabled/` 和 `site-available/` 分开的约定：
- `site-available/` 是"仓库"，存放所有站点配置
- `site-enabled/` 是"启用列表"，通过 symlink 引用仓库中的配置
- 临时下线一个站点只需删除 symlink，不用删文件

### 步骤 4：测试并加载配置

```bash
sudo nginx -t                    # 语法检查（必须！修改配置后先跑这个）
sudo systemctl reload nginx      # 热重载，不中断现有连接
```

### 步骤 5：启动后端并验证

```bash
# 后端监听 127.0.0.1（不对外暴露）
cd /home/rich/stock/stock
conda activate stock
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 另开终端验证
curl http://10.208.141.191/api/health        # → {"status":"ok"}
curl http://10.208.141.191/api/indices       # → 指数列表 JSON
curl http://10.208.141.191/                  # → 前端首页 HTML
```

---

## 四、请求流程（完整数据包路径）

```
1. 远程浏览器输入 http://10.208.141.191/api/health

2. DNS 解析或直接 IP → 网络层路由 → TCP 连接 10.208.141.191:80

3. Nginx 收到 HTTP 请求：
   GET /api/health HTTP/1.1
   Host: 10.208.141.191

4. Nginx 匹配规则：
   - listen 80 ✓
   - server_name 10.208.141.191 ✓
   - location /api/... ✅（匹配 / 前缀）

5. Nginx 创建新请求发给后端：
   GET /api/health HTTP/1.1
   Host: 10.208.141.191          ← 原始 Host（透传）
   X-Real-IP: <客户端IP>          ← 真实 IP（Nginx 添加）
   X-Forwarded-For: <客户端IP>    ← 代理链（Nginx 添加）

6. uvicorn (127.0.0.1:8000) 处理请求，返回：
   HTTP/1.1 200 OK
   {"status": "ok"}

7. Nginx 收到后端响应，原样返回给客户端

8. 浏览器收到 {"status": "ok"}
```

---

## 五、常见问题

### 5.1 静态文件 403 Forbidden

**原因**：Nginx worker 以 `www-data` 用户运行，但项目目录 `/home/rich/` 权限为 750（禁止 other 访问），`www-data` 无法穿越进入项目目录读取文件。

**解决方案**：
- **方案 A**：去掉 Nginx 的静态文件 location，所有请求统一 proxy 到 uvicorn（本项目采用）
- **方案 B**：`chmod o+x /home/rich` 给其他用户执行权限
- **方案 C**：将静态文件复制到 `/var/www/stock/static/`（标准做法）

### 5.2 修改配置后如何生效

```bash
sudo nginx -t                    # 先检查语法
sudo systemctl reload nginx      # 热重载（推荐）
# 或
sudo systemctl restart nginx     # 冷重启（会短暂中断连接）
```

### 5.3 查看日志

```bash
# Nginx 日志
tail -f /var/log/nginx/stock-access.log    # 请求日志
tail -f /var/log/nginx/stock-error.log     # 错误日志

# 后端日志
journalctl -u stock -f                      # 如果用 systemd 管理
# 或直接看终端的 uvicorn 输出
```
