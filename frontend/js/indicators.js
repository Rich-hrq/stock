/** 侧边面板：统计指标、海龟交易法则指标、投资建议 */
(function () {
    "use strict";

    /** 渲染统计面板和指标面板 */
    function renderIndicators(data) {
        renderStats(data);
        renderAdvice(data);
        renderTurtleIndicators(data);
    }

    function renderStats(data) {
        const stats = data.stats || {};
        const container = document.getElementById("statsContent");
        if (!container) return;

        // 判断涨跌
        const returnStr = stats["区间涨跌幅"] || "0%";
        const isUp = returnStr.startsWith("+");

        const dailyStr = stats["日涨跌"] || "—";
        const dailyUp = dailyStr.startsWith("+");

        const prevClose = stats["前日收盘"] != null ? stats["前日收盘"] : "—";

        container.innerHTML = `
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="label">起始价</span>
                    <span class="value">${stats["起价"] ?? "—"}</span>
                </div>
                <div class="stat-item">
                    <span class="label">当前价</span>
                    <span class="value">${stats["收价"] ?? "—"}</span>
                </div>
                <div class="stat-item">
                    <span class="label">最高价</span>
                    <span class="value">${stats["最高价"] ?? "—"}</span>
                </div>
                <div class="stat-item">
                    <span class="label">最低价</span>
                    <span class="value">${stats["最低价"] ?? "—"}</span>
                </div>
                <div class="stat-item">
                    <span class="label">区间涨跌 (O→C)</span>
                    <span class="value ${isUp ? "up" : "down"}">${returnStr}</span>
                </div>
                <div class="stat-item">
                    <span class="label">日涨跌 (P→C)</span>
                    <span class="value ${dailyUp ? "up" : "down"}">${dailyStr}</span>
                </div>
                <div class="stat-item">
                    <span class="label">区间振幅</span>
                    <span class="value">${stats["区间振幅"] ?? "—"}</span>
                </div>
                <div class="stat-item">
                    <span class="label">前日收盘</span>
                    <span class="value">${prevClose}</span>
                </div>
            </div>
        `;
    }

    function renderAdvice(data) {
        const container = document.getElementById("adviceContent");
        if (!container) return;
        container.innerHTML = `<div class="advice-text">${data.advice || "暂无建议"}</div>`;
    }

    function renderTurtleIndicators(data) {
        const container = document.getElementById("indicatorsContent");
        if (!container) return;

        const records = data.data || [];
        if (records.length === 0) {
            container.innerHTML = '<p class="placeholder">数据不足</p>';
            return;
        }

        // 获取最新一期有指标数据的记录
        let lastATR = null;
        let lastBBUpper = null;
        let lastBBMiddle = null;
        let lastBBLower = null;
        let lastDCHigh = null;
        let lastDCLow = null;

        for (let i = records.length - 1; i >= 0; i--) {
            const r = records[i];
            if (lastATR == null && r.atr != null) lastATR = r.atr;
            if (lastBBUpper == null && r.boll_upper != null) lastBBUpper = r.boll_upper;
            if (lastBBMiddle == null && r.boll_middle != null) lastBBMiddle = r.boll_middle;
            if (lastBBLower == null && r.boll_lower != null) lastBBLower = r.boll_lower;
            if (lastDCHigh == null && r.dc_high_20 != null) lastDCHigh = r.dc_high_20;
            if (lastDCLow == null && r.dc_low_20 != null) lastDCLow = r.dc_low_20;
            if (lastATR && lastBBUpper && lastDCHigh) break;
        }

        container.innerHTML = `
            <div class="indicators-grid">
                <div class="indicator-item">
                    <div class="ind-value">${lastATR != null ? lastATR.toFixed(2) : "—"}</div>
                    <div class="ind-label">ATR(20) / N值</div>
                </div>
                <div class="indicator-item">
                    <div class="ind-value">${lastBBMiddle != null ? lastBBMiddle.toFixed(2) : "—"}</div>
                    <div class="ind-label">布林中轨 MA20</div>
                </div>
                <div class="indicator-item">
                    <div class="ind-value">${lastBBUpper != null ? lastBBUpper.toFixed(2) : "—"}</div>
                    <div class="ind-label">布林上轨</div>
                </div>
                <div class="indicator-item">
                    <div class="ind-value">${lastBBLower != null ? lastBBLower.toFixed(2) : "—"}</div>
                    <div class="ind-label">布林下轨</div>
                </div>
                <div class="indicator-item">
                    <div class="ind-value">${lastDCHigh != null ? lastDCHigh.toFixed(2) : "—"}</div>
                    <div class="ind-label">唐奇安上轨(20日)</div>
                </div>
                <div class="indicator-item">
                    <div class="ind-value">${lastDCLow != null ? lastDCLow.toFixed(2) : "—"}</div>
                    <div class="ind-label">唐奇安下轨(20日)</div>
                </div>
            </div>
        `;
    }

    window.renderIndicators = renderIndicators;
})();
