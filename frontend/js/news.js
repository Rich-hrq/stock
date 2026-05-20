/** 新闻资讯页 — 抓取 The Guardian 新闻，按分类展示 */
(function () {
    "use strict";

    const fetchBtn = document.getElementById("fetchNews");
    const emptyState = document.getElementById("emptyState");
    const newsArea = document.getElementById("newsArea");
    const newsMeta = document.getElementById("newsMeta");
    const newsList = document.getElementById("newsList");
    const aiSummary = document.getElementById("aiSummary");
    const aiSummaryBody = document.getElementById("aiSummaryBody");
    const aiSummaryModel = document.getElementById("aiSummaryModel");
    const aiSummaryDiag = document.getElementById("aiSummaryDiag");

    let isFetching = false;

    // ---- 事件绑定 ----
    fetchBtn.addEventListener("click", fetchNews);

    // 页面加载：先获取模型信息（立即显示），再拉取新闻
    fetchModelInfo();
    fetchNews();

    // ---- 获取模型信息 ----
    async function fetchModelInfo() {
        try {
            const res = await fetch("/api/health");
            if (res.ok) {
                const data = await res.json();
                if (aiSummaryModel && data.model) {
                    aiSummaryModel.textContent = data.model;
                }
            }
        } catch (e) {
            if (aiSummaryModel) aiSummaryModel.textContent = "unknown";
        }
    }

    // ---- 获取新闻 ----
    async function fetchNews() {
        if (isFetching) return;

        isFetching = true;
        fetchBtn.disabled = true;
        emptyState.innerHTML = '<span class="loading-spinner"></span> 正在获取新闻...';
        emptyState.style.display = "flex";
        newsArea.style.display = "none";

        try {
            const res = await fetch("/api/guardian_news", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });

            if (!res.ok) {
                const err = await tryParseJson(res);
                throw new Error(err.detail || "请求失败");
            }

            const items = await res.json();

            if (!items || items.length === 0) {
                emptyState.innerHTML = "暂无新闻数据";
                emptyState.style.display = "flex";
                newsArea.style.display = "none";
            } else {
                emptyState.style.display = "none";
                newsArea.style.display = "block";
                renderNews(items);
                await fetchAISummary(items);
            }
        } catch (e) {
            emptyState.innerHTML = escapeHtml("获取失败: " + e.message);
            emptyState.style.display = "flex";
            newsArea.style.display = "none";
        } finally {
            isFetching = false;
            fetchBtn.disabled = false;
        }
    }

    // ---- 渲染新闻列表 ----
    function renderNews(items) {
        newsMeta.innerHTML = `共 <span class="news-count">${items.length}</span> 条新闻`;

        let html = "";
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const num = i + 1;

            const parts = item.link.split("/");
            const category = parts.length > 3 ? parts[3] : "";

            const categoryHtml = category
                ? `<span class="news-category">【${category.toUpperCase()}】</span>`
                : "";

            html += `
                <div class="news-item">
                    <span class="news-number">${num}</span>
                    <div class="news-content">
                        <h2 class="news-title">${categoryHtml}${escapeHtml(item.title)}</h2>
                    </div>
                    <a href="/api/proxy?url=${encodeURIComponent(item.link)}" class="news-link" target="_blank" rel="noopener">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                            <polyline points="15 3 21 3 21 9"/>
                            <line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                        查看原文
                    </a>
                </div>
            `;
        }

        newsList.innerHTML = html;
    }

    // ---- AI 摘要 ----
    async function fetchAISummary(items) {
        // 确保 DOM 元素存在
        if (!aiSummary || !aiSummaryBody) {
            console.warn("AI摘要: DOM元素未找到");
            return;
        }

        aiSummary.style.display = "block";
        aiSummaryBody.innerHTML = '<span class="loading-spinner"></span> 正在生成摘要...';
        if (aiSummaryModel) aiSummaryModel.textContent = "";
        if (aiSummaryDiag) aiSummaryDiag.style.display = "none";

        try {
            const res = await fetch("/api/news/summary", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ headlines: items }),
            });

            // ---- 关键：检查 Content-Type，防止把 HTML 当 JSON 解析 ----
            const contentType = res.headers.get("Content-Type") || "";

            if (!res.ok) {
                // HTTP 错误（502/504 等），nginx 通常返回 HTML 错误页
                const text = await res.text();
                if (contentType.includes("text/html") || text.trimStart().startsWith("<")) {
                    const diag = diagnoseNginxError(res.status, text);
                    showError(diag);
                } else {
                    const err = safeJsonParse(text);
                    showError("服务器返回 " + res.status + "：" + (err.detail || res.statusText));
                }
                return;
            }

            // 200 但 body 是 HTML（极端情况）
            if (contentType.includes("text/html")) {
                showError("服务器返回了 HTML 页面而非 JSON（可能是反向代理错误）");
                return;
            }

            const data = await res.json();

            // 显示模型（无论成功失败都要显示）
            if (aiSummaryModel && data.model) {
                aiSummaryModel.textContent = data.model;
            }

            // 后端返回了错误分类
            if (data.error_reason) {
                const diag = formatErrorReason(data.error_reason);
                showError(diag);
                return;
            }

            // 成功
            aiSummaryBody.innerHTML = formatSummary(data.summary);
        } catch (e) {
            // 网络错误（fetch 本身失败，连 HTTP 响应都没有）
            if (e.name === "TypeError" && e.message.includes("fetch")) {
                showError("网络连接失败，无法访问服务器");
            } else if (e instanceof SyntaxError) {
                showError("服务器返回了非 JSON 格式的响应（可能触发了 nginx 504 超时错误页）");
            } else {
                showError("未知错误：" + e.message);
            }
        }
    }

    // ---- 诊断 nginx 错误页 ----
    function diagnoseNginxError(status, html) {
        const lower = html.toLowerCase();
        if (status === 504 || lower.includes("timeout") || lower.includes("timed out")) {
            return "nginx 网关超时 (504)：LLM 推理耗时超过 nginx 等待上限。可能原因：① 并发请求过多 ② DeepSeek API 响应慢 ③ 网络延迟";
        }
        if (status === 502 || lower.includes("bad gateway")) {
            return "nginx 网关错误 (502)：后端服务暂时不可用。可能原因：① uvicorn 进程重启中 ② 线程池耗尽无法接受新连接";
        }
        if (status === 503 || lower.includes("unavailable")) {
            return "nginx 服务不可用 (503)：服务器过载或维护中";
        }
        return "服务器返回了 HTML 错误页 (HTTP " + status + ")，请检查 nginx 和 uvicorn 状态";
    }

    // ---- 格式化后端的 error_reason ----
    function formatErrorReason(reason) {
        const map = {
            "apikey": "API Key 无效或已过期，请检查 backend/.env 中的 ANTHROPIC_API_KEY",
            "timeout": "LLM 请求超时（45s）。可能原因：① 并发过高导致线程池排队 ② DeepSeek API 响应慢 ③ 网络延迟",
            "ratelimit": "API 请求被限流 (429)。DeepSeek API 拒绝了过多并发请求",
            "model": "模型名称无效或不可用，请检查 ANTHROPIC_MODEL 配置",
            "network": "网络连接失败，无法访问 DeepSeek API。请检查代理和 DNS",
            "unknown": "发生未知错误，请查看服务器日志",
        };
        return map[reason] || "未知错误分类: " + reason;
    }

    function showError(diagText) {
        aiSummaryBody.innerHTML = '<span style="color:var(--text-dim);">摘要生成失败</span>';
        if (aiSummaryDiag) {
            aiSummaryDiag.style.display = "block";
            aiSummaryDiag.innerHTML = "<strong>诊断：</strong>" + escapeHtml(diagText);
        }
    }

    function formatSummary(text) {
        return escapeHtml(text)
            .replace(/\n\n/g, "<br><br>")
            .replace(/\n/g, "<br>")
            .replace(/【(.+?)】/g, "<strong>【$1】</strong>");
    }

    // ---- 安全的 JSON 解析 ----
    async function tryParseJson(res) {
        const text = await res.text();
        return safeJsonParse(text);
    }

    function safeJsonParse(text) {
        try {
            return JSON.parse(text);
        } catch (e) {
            return { detail: text.substring(0, 200) };
        }
    }

    // ---- 工具函数 ----
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
