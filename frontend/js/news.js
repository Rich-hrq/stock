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

    let isFetching = false;

    // ---- 事件绑定 ----
    fetchBtn.addEventListener("click", fetchNews);

    // 页面加载后自动拉取一次
    fetchNews();

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
                const err = await res.json();
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
                fetchAISummary(items);
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

            // 从链接提取分类
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
        const card = document.getElementById("aiSummary");
        const body = document.getElementById("aiSummaryBody");

        if (!card || !body) {
            console.warn("AI摘要: DOM元素未找到 — aiSummary=" + !!card + " aiSummaryBody=" + !!body + "（可能是浏览器缓存了旧HTML，请 Cmd+Shift+R 强制刷新）");
            return;
        }

        card.style.display = "block";
        body.innerHTML = '<span class="loading-spinner"></span> 正在生成摘要...';

        try {
            const res = await fetch("/api/news/summary", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ headlines: items }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "摘要生成失败");
            }

            const data = await res.json();
            body.innerHTML = formatSummary(data.summary);
        } catch (e) {
            body.innerHTML = `<span style="color:var(--text-dim);">摘要生成失败：${escapeHtml(e.message)}</span>`;
        }
    }

    function formatSummary(text) {
        // 先转义，再处理换行和标题加粗
        return escapeHtml(text)
            .replace(/\n\n/g, "<br><br>")
            .replace(/\n/g, "<br>")
            .replace(/【(.+?)】/g, "<strong>【$1】</strong>");
    }

    // ---- 工具函数 ----
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
