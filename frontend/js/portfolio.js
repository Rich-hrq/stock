/** 持仓记录页面：登录/注册、交易管理、持仓汇总计算 */
(function () {
    "use strict";

    // ---- 常量 ----
    const INDEX_NAMES = {
        "^GSPC": "标普500",
        "^NDX": "纳斯达克100",
        "^IXIC": "纳斯达克综合",
        "^DJI": "道琼斯工业",
    };

    // ---- DOM ----
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ---- Token 管理 ----
    function getToken() {
        return localStorage.getItem("portfolio_token");
    }
    function setToken(token) {
        localStorage.setItem("portfolio_token", token);
    }
    function removeToken() {
        localStorage.removeItem("portfolio_token");
    }

    // ---- API 请求封装 ----
    async function api(url, options = {}) {
        const token = getToken();
        const headers = { "Content-Type": "application/json", ...options.headers };
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
        const resp = await fetch(url, { ...options, headers });
        if (resp.status === 401) {
            removeToken();
            showAuthView();
            throw new Error("登录已过期，请重新登录");
        }
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `请求失败 (${resp.status})`);
        }
        return resp.json();
    }

    // ---- 视图切换 ----
    function showAuthView() {
        $("#authView").style.display = "flex";
        $("#mainView").style.display = "none";
        renderTopbar(null);
    }

    function showMainView(username) {
        $("#authView").style.display = "none";
        $("#mainView").style.display = "block";
        renderTopbar(username);
        // 默认日期为今天，默认金额 200
        $("#txDate").value = new Date().toISOString().split("T")[0];
        $("#txAmount").value = "200";
        refreshData();
    }

    function renderTopbar(username) {
        const el = $("#topbarRight");
        if (username) {
            el.innerHTML = `
                <span class="topbar-user">${username}</span>
                <button class="btn-logout" id="btnLogout">退出</button>
            `;
            $("#btnLogout").addEventListener("click", () => {
                removeToken();
                showAuthView();
            });
        } else {
            el.innerHTML = "";
        }
    }

    // ---- 登录/注册 ----
    let currentTab = "login"; // login | register

    function initAuth() {
        // Tab 切换
        $$(".auth-tab").forEach((btn) => {
            btn.addEventListener("click", () => {
                currentTab = btn.dataset.tab;
                $$(".auth-tab").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                $("#authSubmit").textContent = currentTab === "login" ? "登录" : "注册";
                $("#authError").textContent = "";
            });
        });

        // 表单提交
        $("#authForm").addEventListener("submit", async (e) => {
            e.preventDefault();
            const username = $("#authUsername").value.trim();
            const password = $("#authPassword").value;
            const errEl = $("#authError");
            errEl.textContent = "";

            if (!username || !password) {
                errEl.textContent = "请填写用户名和密码";
                return;
            }

            const endpoint = currentTab === "login" ? "/api/auth/login" : "/api/auth/register";
            try {
                const data = await api(endpoint, {
                    method: "POST",
                    body: JSON.stringify({ username, password }),
                });
                setToken(data.access_token);
                // 获取用户名
                const me = await api("/api/auth/me");
                showMainView(me.username);
            } catch (err) {
                errEl.textContent = err.message;
            }
        });
    }

    // ---- 交易表单 ----
    function initTradeForm() {
        $("#tradeForm").addEventListener("submit", async (e) => {
            e.preventDefault();
            const errEl = $("#tradeError");
            errEl.textContent = "";

            const symbol = $("#txSymbol").value;
            const direction = $("#txDirection").value;
            const tradeDate = $("#txDate").value;
            const amount = parseFloat($("#txAmount").value);

            if (!tradeDate || !amount || amount <= 0) {
                errEl.textContent = "请填写完整的交易信息";
                return;
            }

            try {
                await api("/api/portfolio/transactions", {
                    method: "POST",
                    body: JSON.stringify({
                        symbol,
                        direction,
                        trade_date: tradeDate,
                        amount_cny: amount,
                    }),
                });
                $("#txAmount").value = "";
                refreshData();
            } catch (err) {
                errEl.textContent = err.message;
            }
        });
    }

    // ---- 数据刷新 ----
    async function refreshData() {
        await Promise.all([
            loadSummary(),
            loadHistory(),
            executePlans().then(() => loadPlans()),
        ]);
    }

    // ---- 持仓汇总 ----
    async function loadSummary() {
        try {
            const data = await api("/api/portfolio/summary");
            renderSummary(data);
        } catch (err) {
            console.error("加载持仓汇总失败:", err);
        }
    }

    function renderSummary(data) {
        const container = $("#summaryCards");
        const emptyEl = $("#summaryEmpty");

        if (!data.positions || data.positions.length === 0) {
            container.innerHTML = "";
            emptyEl.style.display = "block";
            return;
        }

        emptyEl.style.display = "none";
        container.innerHTML = data.positions
            .map((p) => {
                const pnlClass = (v) => (parseFloat(v) >= 0 ? "pnl-positive" : "pnl-negative");
                const pnlSign = (v) => (parseFloat(v) >= 0 ? "+" : "");
                return `
                <div class="summary-card">
                    <div class="card-header">
                        <span class="card-name">${p.name}</span>
                        <span class="card-symbol">${p.symbol}</span>
                    </div>
                    <div class="summary-row">
                        <span class="label">持仓份额</span>
                        <span class="value">${parseFloat(p.shares).toFixed(6)}</span>
                    </div>
                    <div class="summary-row">
                        <span class="label">加权成本</span>
                        <span class="value">¥${parseFloat(p.avg_cost_cny).toFixed(2)}/份</span>
                    </div>
                    <div class="summary-row">
                        <span class="label">持仓成本</span>
                        <span class="value">¥${parseFloat(p.total_cost_cny).toFixed(2)}</span>
                    </div>
                    <hr class="summary-divider">
                    <div class="summary-row">
                        <span class="label">已实现净赚</span>
                        <span class="value ${pnlClass(p.realized_pnl_cny)}">${pnlSign(p.realized_pnl_cny)}¥${Math.abs(parseFloat(p.realized_pnl_cny)).toFixed(2)}</span>
                    </div>
                    <div class="summary-row">
                        <span class="label">当前价格</span>
                        <span class="value">$${parseFloat(p.current_price_usd).toFixed(2)} (汇率 ${parseFloat(p.current_rate).toFixed(4)})</span>
                    </div>
                    <div class="summary-row">
                        <span class="label">当日清仓价值</span>
                        <span class="value">¥${parseFloat(p.liquidation_value_cny).toFixed(2)}</span>
                    </div>
                    <hr class="summary-divider">
                    <div class="summary-row">
                        <span class="label">未实现盈亏</span>
                        <span class="value ${pnlClass(p.unrealized_pnl_cny)}">${pnlSign(p.unrealized_pnl_cny)}¥${Math.abs(parseFloat(p.unrealized_pnl_cny)).toFixed(2)}</span>
                    </div>
                    <div class="summary-row">
                        <span class="label">总盈亏</span>
                        <span class="value ${pnlClass(p.total_pnl_cny)}" style="font-size:15px;font-weight:700;">${pnlSign(p.total_pnl_cny)}¥${Math.abs(parseFloat(p.total_pnl_cny)).toFixed(2)}</span>
                    </div>
                </div>
                `;
            })
            .join("");
    }

    // ---- 交易历史 ----
    async function loadHistory() {
        try {
            const data = await api("/api/portfolio/transactions");
            renderHistory(data);
        } catch (err) {
            console.error("加载交易历史失败:", err);
        }
    }

    function renderHistory(txs) {
        const container = $("#historyTable");
        const emptyEl = $("#historyEmpty");

        if (!txs || txs.length === 0) {
            container.innerHTML = "";
            emptyEl.style.display = "block";
            return;
        }

        emptyEl.style.display = "none";
        const rows = txs
            .map((tx) => {
                const dirClass = tx.direction === "buy" ? "direction-buy" : "direction-sell";
                const dirText = tx.direction === "buy" ? "买入" : "卖出";
                return `
                <tr>
                    <td>${tx.trade_date}</td>
                    <td>${INDEX_NAMES[tx.symbol] || tx.symbol}</td>
                    <td class="${dirClass}">${dirText}</td>
                    <td>¥${parseFloat(tx.amount_cny).toFixed(2)}</td>
                    <td>$${parseFloat(tx.close_price_usd).toFixed(2)}</td>
                    <td>${parseFloat(tx.exchange_rate).toFixed(4)}</td>
                    <td>${parseFloat(tx.shares).toFixed(6)}</td>
                    <td><button class="btn-delete" data-id="${tx.id}">删除</button></td>
                </tr>
                `;
            })
            .join("");

        container.innerHTML = `
            <table class="history-table">
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>指数</th>
                        <th>方向</th>
                        <th>金额 (¥)</th>
                        <th>收盘价 ($)</th>
                        <th>汇率</th>
                        <th>份额</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;

        // 删除按钮事件
        container.querySelectorAll(".btn-delete").forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (!confirm("确定删除这笔交易记录？删除后持仓将自动重算。")) return;
                try {
                    await api(`/api/portfolio/transactions/${btn.dataset.id}`, {
                        method: "DELETE",
                    });
                    refreshData();
                } catch (err) {
                    alert(err.message);
                }
            });
        });
    }

    // ---- 定投计划 ----
    const WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

    function initPlanForm() {
        // 频率切换：显示/隐藏周几/几号
        $("#planFreq").addEventListener("change", () => {
            const freq = $("#planFreq").value;
            $("#planDayWeekGroup").style.display = freq === "weekly" ? "" : "none";
            $("#planDayMonthGroup").style.display = freq === "monthly" ? "" : "none";
        });

        $("#planForm").addEventListener("submit", async (e) => {
            e.preventDefault();
            const errEl = $("#planError");
            errEl.textContent = "";

            const symbol = $("#planSymbol").value;
            const amount = parseFloat($("#planAmount").value);
            const frequency = $("#planFreq").value;
            const day_of_week = parseInt($("#planDayWeek").value);
            const day_of_month = parseInt($("#planDayMonth").value);

            if (!amount || amount <= 0) {
                errEl.textContent = "请填写有效金额";
                return;
            }

            const body = { symbol, amount_cny: amount, frequency };
            if (frequency === "weekly") body.day_of_week = day_of_week;
            else body.day_of_month = day_of_month;

            try {
                await api("/api/portfolio/plans", {
                    method: "POST",
                    body: JSON.stringify(body),
                });
                $("#planAmount").value = "200";
                $("#planError").textContent = "";
                loadPlans();
            } catch (err) {
                errEl.textContent = err.message;
            }
        });
    }

    async function executePlans() {
        try {
            const result = await api("/api/portfolio/plans/execute", { method: "POST" });
            if (result.executed > 0) {
                // 有新的自动交易，静默刷新历史
                return;
            }
        } catch (err) {
            console.error("执行定投计划失败:", err);
        }
    }

    async function loadPlans() {
        try {
            const data = await api("/api/portfolio/plans");
            renderPlans(data);
        } catch (err) {
            console.error("加载定投计划失败:", err);
        }
    }

    function renderPlans(plans) {
        const container = $("#planList");
        const emptyEl = $("#planEmpty");

        if (!plans || plans.length === 0) {
            container.innerHTML = "";
            emptyEl.style.display = "block";
            return;
        }

        emptyEl.style.display = "none";
        container.innerHTML = plans
            .map((p) => {
                const freqText = p.frequency === "weekly"
                    ? `每周${WEEKDAY_NAMES[p.day_of_week] || p.day_of_week}`
                    : `每月${p.day_of_month}号`;
                const statusText = p.enabled ? "启用中" : "已暂停";
                const statusClass = p.enabled ? "plan-active" : "plan-paused";
                return `
                <div class="plan-card">
                    <div class="plan-info">
                        <span class="plan-symbol">${INDEX_NAMES[p.symbol] || p.symbol}</span>
                        <span class="plan-detail">${freqText} 买入 ¥${parseFloat(p.amount_cny).toFixed(2)}</span>
                        <span class="plan-status ${statusClass}">${statusText}</span>
                    </div>
                    <div class="plan-actions">
                        <button class="btn-sm btn-toggle" data-id="${p.id}" data-action="toggle">
                            ${p.enabled ? "暂停" : "启用"}
                        </button>
                        <button class="btn-sm btn-delete" data-id="${p.id}" data-action="delete">删除</button>
                    </div>
                </div>
                `;
            })
            .join("");

        // 绑定按钮事件
        container.querySelectorAll("[data-action='toggle']").forEach((btn) => {
            btn.addEventListener("click", async () => {
                try {
                    await api(`/api/portfolio/plans/${btn.dataset.id}/toggle`, {
                        method: "PATCH",
                    });
                    loadPlans();
                } catch (err) {
                    alert(err.message);
                }
            });
        });

        container.querySelectorAll("[data-action='delete']").forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (!confirm("确定删除这个定投计划？")) return;
                try {
                    await api(`/api/portfolio/plans/${btn.dataset.id}`, { method: "DELETE" });
                    loadPlans();
                } catch (err) {
                    alert(err.message);
                }
            });
        });
    }

    // ---- 初始化 ----
    async function init() {
        initAuth();
        initTradeForm();
        initPlanForm();

        // 检查登录状态
        const token = getToken();
        if (token) {
            try {
                const me = await api("/api/auth/me");
                showMainView(me.username);
            } catch {
                showAuthView();
            }
        } else {
            showAuthView();
        }
    }

    init();
})();
