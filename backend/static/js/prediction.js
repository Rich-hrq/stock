/** Polymarket 预测市场 — 每 market 一页，翻页浏览 */
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
    const eventBadge = document.getElementById("eventBadge");

    let markets = [];        // 扁平化后的所有 market
    let currentIdx = 0;
    let isSearching = false;

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

        const keywords = raw.split(/[,，\s]+/).map((k) => k.trim()).filter(Boolean);
        if (keywords.length === 0) return;

        isSearching = true;
        searchBtn.disabled = true;
        emptyState.innerHTML = '<span class="loading-spinner"></span> 查询中...';
        emptyState.style.display = "flex";
        cardArea.style.display = "none";

        try {
            const res = await fetch("/api/predict", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    keywords,
                    limit: parseInt(limitInput.value) || 500,
                    threshold: parseInt(thresholdInput.value) || 0,
                }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "请求失败");
            }

            const events = await res.json();
            markets = flatten(events);
            currentIdx = 0;

            if (markets.length === 0) {
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

    // ---- 扁平化：每个 market 一条记录，携带父事件信息 ----
    function flatten(events) {
        const result = [];
        for (const ev of events) {
            for (const m of ev.markets || []) {
                result.push({
                    eventTitle: ev.title || "",
                    eventDesc: ev.description || "",
                    meta: ev.meta || {},
                    question: m.question || "",
                    endDate: m.endDate || "",
                    description: m.description || "",
                    outcomePrices: m.outcomePrices || "",
                    volume: parseFloat(m.volume) || 0,
                });
            }
        }
        return result;
    }

    // ---- 渲染当前 market 卡片 ----
    function renderCurrent() {
        if (markets.length === 0) return;

        const m = markets[currentIdx];
        const total = markets.length;

        // 页面指示器
        pageIndicator.textContent = `${currentIdx + 1} / ${total}`;
        eventBadge.textContent = m.eventTitle || "—";

        // 上一页/下一页 按钮状态
        prevBtn.disabled = currentIdx === 0;
        nextBtn.disabled = currentIdx === total - 1;

        // 组装卡片 HTML（写入 cardContent，不覆盖翻页控件）
        cardContent.innerHTML = `
            <div class="market-card-full">
                <div class="card-question">${escapeHtml(m.question)}</div>

                <div class="card-meta-row">
                    <div class="card-meta-item">
                        <span class="card-meta-label">截止日期</span>
                        <span class="card-meta-value">${formatDate(m.endDate)}</span>
                    </div>
                    <div class="card-meta-item">
                        <span class="card-meta-label">交易量</span>
                        <span class="card-meta-value accent">${formatVolume(m.volume)}</span>
                    </div>
                </div>

                <div class="card-outcomes">
                    ${renderOutcomeBars(m.outcomePrices)}
                </div>

                ${m.description
                    ? `<div class="card-description">
                        <h4>市场说明</h4>
                        <p>${escapeHtml(m.description)}</p>
                    </div>`
                    : ""}

                ${m.meta.context_description
                    ? `<div class="card-context">
                        <h4>背景信息</h4>
                        <p>${escapeHtml(m.meta.context_description)}</p>
                        ${m.meta.context_updated_at
                            ? `<span class="context-time">更新于 ${formatDate(m.meta.context_updated_at)}</span>`
                            : ""}
                    </div>`
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
                    <div class="outcome-bar-group">
                        <div class="outcome-bar-header">
                            <span class="outcome-name">${label}</span>
                            <span class="outcome-pct">${pct}%</span>
                        </div>
                        <div class="outcome-bar-track">
                            <div class="outcome-bar-fill" style="width:${pct}%; background:${color};"></div>
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    // ---- 翻页 ----
    function navigate(delta) {
        const newIdx = currentIdx + delta;
        if (newIdx < 0 || newIdx >= markets.length) return;
        currentIdx = newIdx;
        renderCurrent();
    }

    // ---- 工具函数 ----
    function parseOutcomePrices(raw) {
        try {
            const arr = JSON.parse(raw);
            return arr.map(parseFloat).filter((n) => !isNaN(n));
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

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
