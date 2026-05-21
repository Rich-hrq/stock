/** Polymarket 预测市场 — 按 event 分组翻页，关键词 + 活跃日期高亮 */
(function () {
    "use strict";

    const keywordInput = document.getElementById("keywordInput");
    const searchBtn = document.getElementById("searchPrediction");
    const limitInput = document.getElementById("predLimit");
    const thresholdInput = document.getElementById("predThreshold");
    const emptyState = document.getElementById("emptyState");
    const cardArea = document.getElementById("cardArea");
    const cardContent = document.getElementById("cardContent");
    const prevBtn = document.getElementById("prevMarket");
    const nextBtn = document.getElementById("nextMarket");
    const pageIndicator = document.getElementById("pageIndicator");
    const modeSearch = document.getElementById("modeSearch");
    const modeList = document.getElementById("modeList");

    let events = [];          // 按 event 分组（不再扁平化）
    let keywords = [];        // 当前搜索词，用于高亮
    let currentIdx = 0;
    let isSearching = false;
    let searchMode = true;    // true = 搜索模式, false = 列表模式

    // ---- 模式切换 ----
    function setMode(isSearch) {
        searchMode = isSearch;
        modeSearch.classList.toggle("active", isSearch);
        modeList.classList.toggle("active", !isSearch);
        if (isSearch) {
            limitInput.value = 20;
            thresholdInput.value = 0;
        } else {
            limitInput.value = 500;
            thresholdInput.value = 100000;
        }
    }

    modeSearch.addEventListener("click", () => setMode(true));
    modeList.addEventListener("click", () => setMode(false));

    // ---- 事件绑定 ----
    searchBtn.addEventListener("click", search);
    keywordInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); search(); }
    });
    prevBtn.addEventListener("click", () => navigate(-1));
    nextBtn.addEventListener("click", () => navigate(1));
    document.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft") navigate(-1);
        if (e.key === "ArrowRight") navigate(1);
    });

    // ---- 查询 ----
    async function search() {
        const raw = keywordInput.value.trim();
        if (!raw || isSearching) return;

        keywords = raw.split(/[,，\s]+/).map((k) => k.trim()).filter(Boolean);
        if (keywords.length === 0) return;

        isSearching = true;
        searchBtn.disabled = true;
        emptyState.innerHTML = '<span class="loading-spinner"></span> 查询中...';
        emptyState.style.display = "flex";
        cardArea.style.display = "none";

        try {
            let res;
            if (searchMode) {
                // 搜索模式：调用 /public-search 端点
                res = await fetch("/api/predict/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        query: keywords.join(" "),
                        limit_per_type: parseInt(limitInput.value) || 20,
                        threshold: parseInt(thresholdInput.value) || 0,
                    }),
                });
            } else {
                // 列表模式：调用原接口
                res = await fetch("/api/predict", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        keywords,
                        limit: parseInt(limitInput.value) || 500,
                        threshold: parseInt(thresholdInput.value) || 0,
                    }),
                });
            }

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "请求失败");
            }

            events = await res.json();
            currentIdx = 0;

            if (events.length === 0) {
                emptyState.innerHTML = "未找到匹配的预测事件";
                emptyState.style.display = "flex";
                cardArea.style.display = "none";
            } else {
                emptyState.style.display = "none";
                cardArea.style.display = "flex";
                renderCurrent();
            }
        } catch (e) {
            emptyState.innerHTML = escapeHtml("查询失败: " + e.message);
            emptyState.style.display = "flex";
            cardArea.style.display = "none";
        } finally {
            isSearching = false;
            searchBtn.disabled = false;
        }
    }

    // ---- 渲染当前 event ----
    function renderCurrent() {
        if (events.length === 0) return;

        const ev = events[currentIdx];
        const total = events.length;

        pageIndicator.textContent = `${currentIdx + 1} / ${total}`;
        prevBtn.disabled = currentIdx === 0;
        nextBtn.disabled = currentIdx === total - 1;

        const markets = ev.markets || [];
        const meta = ev.meta || {};

        cardContent.innerHTML = `
            <div class="event-card-full">
                <div class="event-card-header">
                    <h2 class="event-card-title">${hl(ev.title)}</h2>
                    ${ev.description
                        ? `<p class="event-card-desc">${hl(truncate(ev.description, 400))}</p>`
                        : ""}
                </div>

                <div class="markets-section">
                    <h3 class="markets-heading">
                        预测市场 <span class="markets-count">${markets.length}</span>
                        <span class="markets-summary">
                            （进行中 ${markets.filter(m => isActive(m.endDate)).length}，已截止 ${markets.filter(m => !isActive(m.endDate)).length}）
                        </span>
                    </h3>
                    ${markets.map((m) => renderMarketCard(m)).join("")}
                </div>

                ${meta.context_description
                    ? `<div class="event-context">
                        <h4>背景信息</h4>
                        <p>${hl(meta.context_description)}</p>
                        ${meta.context_updated_at
                            ? `<span class="context-time">更新于 ${formatDate(meta.context_updated_at)}</span>`
                            : ""}
                    </div>`
                    : ""}
            </div>
        `;
    }

    // ---- 渲染单个 market 子卡片 ----
    function renderMarketCard(m) {
        const active = isActive(m.endDate);
        const statusClass = active ? "active" : "expired";
        const statusText = active ? "进行中" : "已截止";

        return `
            <div class="market-subcard ${statusClass}">
                <div class="market-subcard-header">
                    <span class="market-question">${hl(m.question || "—")}</span>
                    <span class="status-badge ${statusClass}">${statusText}</span>
                </div>

                <div class="market-subcard-meta">
                    <span class="meta-item">
                        <span class="meta-label">截止</span>
                        <span class="meta-value ${active ? "date-active" : ""}">${formatDate(m.endDate)}</span>
                    </span>
                    <span class="meta-item">
                        <span class="meta-label">交易量</span>
                        <span class="meta-value accent">${formatVolume(parseFloat(m.volume) || 0)}</span>
                    </span>
                </div>

                <div class="market-outcomes">
                    ${renderOutcomeBars(m.outcomePrices || "")}
                </div>

                ${m.description
                    ? `<div class="market-desc">${hl(truncate(m.description, 200))}</div>`
                    : ""}
            </div>
        `;
    }

    function renderOutcomeBars(raw) {
        const prices = parseOutcomePrices(raw);
        if (prices.length === 0) return "";

        return prices
            .map((p, i) => {
                const pct = (p * 100).toFixed(1);
                const label = outcomeLabel(i);
                const color = p > 0.5 ? "var(--green)" : p < 0.5 ? "var(--red)" : "var(--text-dim)";
                return `
                    <div class="outcome-row">
                        <span class="outcome-name">${label}</span>
                        <div class="outcome-track">
                            <div class="outcome-fill" style="width:${pct}%; background:${color};"></div>
                        </div>
                        <span class="outcome-pct">${pct}%</span>
                    </div>
                `;
            })
            .join("");
    }

    // ---- 翻页 ----
    function navigate(delta) {
        const newIdx = currentIdx + delta;
        if (newIdx < 0 || newIdx >= events.length) return;
        currentIdx = newIdx;
        renderCurrent();
    }

    // ========== 高亮 ==========

    /** 对文本做 HTML 转义后高亮所有搜索关键词 */
    function hl(text) {
        if (!text) return "";
        let out = escapeHtml(text);
        const pattern = keywords
            .map((k) => escapeRegex(k.trim()))
            .filter(Boolean)
            .join("|");
        if (!pattern) return out;
        return out.replace(
            new RegExp(`(${pattern})`, "gi"),
            '<mark class="kw-highlight">$1</mark>'
        );
    }

    function isActive(isoDate) {
        if (!isoDate) return false;
        return new Date(isoDate) > new Date();
    }

    // ========== 工具函数 ==========

    function parseOutcomePrices(raw) {
        try {
            return JSON.parse(raw).map(parseFloat).filter((n) => !isNaN(n));
        } catch { return []; }
    }

    function outcomeLabel(idx) {
        return idx === 0 ? "Yes" : idx === 1 ? "No" : `Outcome ${idx + 1}`;
    }

    function formatVolume(vol) {
        if (vol >= 1e6) return "$" + (vol / 1e6).toFixed(2) + "M";
        if (vol >= 1e3) return "$" + (vol / 1e3).toFixed(1) + "K";
        return "$" + vol.toFixed(2);
    }

    function formatDate(iso) {
        if (!iso) return "—";
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso.slice(0, 10);
        return d.toISOString().slice(0, 10);
    }

    function truncate(text, max) {
        if (!text) return "";
        return text.length > max ? text.slice(0, max) + "…" : text;
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeRegex(s) {
        return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }
})();
