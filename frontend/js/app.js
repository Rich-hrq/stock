/** 应用主入口：初始化指数标签、时间选择器，协调数据加载和视图更新 */
(function () {
    "use strict";

    // ---- 状态 ----
    const state = {
        indices: [],          // [{symbol, name}]
        currentSymbol: null,  // "^GSPC"
        currentDays: 180,     // 默认6个月
        startDate: null,      // 自定义起始日期
        endDate: null,        // 自定义截止日期
        isLoading: false,
    };

    // ---- DOM 引用 ----
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ---- 初始化 ----
    async function init() {
        // 获取指数列表
        try {
            const res = await fetch("/api/indices");
            const data = await res.json();
            state.indices = data.indices;
            state.currentSymbol = state.indices[0]?.symbol || null;
        } catch (e) {
            console.error("获取指数列表失败:", e);
            state.indices = [
                { symbol: "^GSPC", name: "标普500" },
                { symbol: "^NDX", name: "纳斯达克100" },
                { symbol: "^IXIC", name: "纳斯达克综合指数" },
                { symbol: "^DJI", name: "道琼斯工业指数" },
            ];
            state.currentSymbol = "^GSPC";
        }

        renderIndexTabs();
        bindEvents();
        loadData();
    }

    // ---- 渲染指数标签 ----
    function renderIndexTabs() {
        const container = $("#indexTabs");
        container.innerHTML = state.indices
            .map(
                (idx) =>
                    `<button data-symbol="${idx.symbol}" class="${idx.symbol === state.currentSymbol ? "active" : ""}">${idx.name}</button>`
            )
            .join("");
    }

    // ---- 事件绑定 ----
    function bindEvents() {
        // 指数标签切换
        $("#indexTabs").addEventListener("click", (e) => {
            const btn = e.target.closest("button");
            if (!btn) return;
            state.currentSymbol = btn.dataset.symbol;
            renderIndexTabs();
            loadData();
        });

        // 时间预设按钮
        $("#timePresets").addEventListener("click", (e) => {
            const btn = e.target.closest("button");
            if (!btn) return;
            state.currentDays = parseInt(btn.dataset.days);
            state.startDate = null;
            state.endDate = null;
            $("#timePresets").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            loadData();
        });

        // 自定义日期
        $("#applyDate").addEventListener("click", () => {
            const startVal = $("#startDate").value;
            const endVal = $("#endDate").value;
            if (startVal && endVal) {
                state.startDate = startVal;
                state.endDate = endVal;
                state.currentDays = 0;
                $("#timePresets").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
                loadData();
            }
        });
    }

    // ---- 加载数据 ----
    async function loadData() {
        if (state.isLoading) return;
        state.isLoading = true;

        // 计算日期参数
        let startDate, endDate;
        if (state.startDate && state.endDate) {
            startDate = state.startDate;
            endDate = state.endDate;
        } else {
            const today = new Date();
            endDate = today.toISOString().slice(0, 10);
            const start = new Date(today);
            start.setDate(start.getDate() - state.currentDays);
            startDate = start.toISOString().slice(0, 10);
        }

        // 自动填入日期选择器
        $("#startDate").value = startDate;
        $("#endDate").value = endDate;

        try {
            const url = `/api/indices/${encodeURIComponent(state.currentSymbol)}/analysis?start_date=${startDate}&end_date=${endDate}`;
            const res = await fetch(url);
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "加载失败");
            }
            const data = await res.json();

            // 更新图表
            if (typeof renderChart === "function") {
                renderChart(data);
            }
            // 更新指标面板
            if (typeof renderIndicators === "function") {
                renderIndicators(data);
            }
        } catch (e) {
            console.error("数据加载失败:", e);
            showError(e.message);
        } finally {
            state.isLoading = false;
        }
    }

    function showError(msg) {
        // 简单的错误提示
        const chartDom = $("#mainChart");
        if (chartDom) {
            chartDom.innerHTML = `<div style="text-align:center;padding:60px;color:var(--text-dim);">加载失败：${msg}</div>`;
        }
    }

    // 暴露 loadData 供外部调用
    window.appState = state;
    window.reloadData = loadData;

    // 启动
    document.addEventListener("DOMContentLoaded", init);
})();
