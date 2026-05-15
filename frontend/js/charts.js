/** ECharts 图表渲染：分组切换（走势线 / 均线 / K线+量 / 布林带 / 唐奇安） */
(function () {
    "use strict";

    var chartInstance = null;

    // 分组状态：price 始终开启不可切换
    var groupState = {
        price: true,
        ma: true,
        candlestick: false,
        bollinger: false,
        donchian: false,
    };

    // 各组的 series 定义缓存
    var cachedGroups = {};
    // 非 series 配置缓存
    var cachedBaseOption = null;

    // 各 series 的图例颜色映射
    var legendColors = {
        "走势线":      { type: "dot",  color: "#e0e6ed" },
        "MA5":         { type: "dot",  color: "#ffb74d" },
        "MA10":        { type: "dot",  color: "#ce93d8" },
        "MA20":        { type: "dot",  color: "#ffd54f" },
        "K线":         { type: "dot",  color: "#4caf50" },
        "成交量":       { type: "dot",  color: "#8899aa" },
        "布林上轨":     { type: "dash", color: "rgba(239,83,80,0.8)" },
        "布林下轨":     { type: "dash", color: "rgba(76,175,80,0.8)" },
        "唐奇安上轨(20)": { type: "dot",  color: "rgba(79,195,247,0.6)" },
        "唐奇安下轨(20)": { type: "dot",  color: "rgba(79,195,247,0.6)" },
    };

    /** 初始化或获取 ECharts 实例 */
    function getChart() {
        var dom = document.getElementById("mainChart");
        if (!dom) return null;
        if (chartInstance) {
            chartInstance.resize();
            return chartInstance;
        }
        chartInstance = echarts.init(dom, "dark");
        window.addEventListener("resize", function () { chartInstance && chartInstance.resize(); });
        return chartInstance;
    }

    /** 从缓存中按 groupState 拼装可见 series（去重），并更新内联图例 */
    function applyVisibility() {
        if (!chartInstance || !cachedBaseOption) return;

        var seen = {};
        var visibleSeries = [];

        Object.keys(groupState).forEach(function (g) {
            if (!groupState[g] || !cachedGroups[g]) return;
            cachedGroups[g].forEach(function (s) {
                if (!seen[s.name]) {
                    seen[s.name] = true;
                    visibleSeries.push(s);
                }
            });
        });

        var fullOption = Object.assign({}, cachedBaseOption, { series: visibleSeries });
        chartInstance.setOption(fullOption, true);
        updateButtons();
        updateInlineLegend();
    }

    /** 切换分组显隐 */
    function toggleGroup(group) {
        if (group === "price") return;
        groupState[group] = !groupState[group];
        applyVisibility();
    }

    /** 更新按钮 active 样式 */
    function updateButtons() {
        var btns = document.querySelectorAll(".toggle-btn");
        for (var i = 0; i < btns.length; i++) {
            var btn = btns[i];
            var g = btn.getAttribute("data-group");
            if (g === "price") continue;
            if (groupState[g]) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        }
    }

    /** 更新内联图例（彩色圆点 + 系列名） */
    function updateInlineLegend() {
        var container = document.getElementById("chartLegendInline");
        if (!container) return;

        var seen = {};
        var items = [];

        Object.keys(groupState).forEach(function (g) {
            if (!groupState[g] || !cachedGroups[g]) return;
            cachedGroups[g].forEach(function (s) {
                if (seen[s.name]) return;
                seen[s.name] = true;
                var cfg = legendColors[s.name];
                if (!cfg) return;
                if (cfg.type === "dash") {
                    items.push('<span class="legend-item"><span class="legend-dash" style="border-color:' + cfg.color + '"></span>' + s.name + '</span>');
                } else {
                    items.push('<span class="legend-item"><span class="legend-dot" style="background:' + cfg.color + '"></span>' + s.name + '</span>');
                }
            });
        });

        container.innerHTML = items.join("");
    }

    /** 绑定按钮点击事件 */
    function bindToggles() {
        var container = document.getElementById("chartToggles");
        if (!container) return;
        container.addEventListener("click", function (e) {
            var btn = e.target.closest("button");
            if (!btn) return;
            var group = btn.getAttribute("data-group");
            if (group) toggleGroup(group);
        });
    }

    bindToggles();

    /** 主渲染函数 */
    function renderChart(data) {
        var chart = getChart();
        if (!chart) return;

        var records = data.data || [];
        if (records.length === 0) {
            cachedGroups = {};
            cachedBaseOption = null;
            chart.setOption({
                title: { text: "暂无数据", left: "center", top: "center", textStyle: { color: "#8899aa" } },
            }, true);
            updateInlineLegend();
            return;
        }

        // ---- 日期格式化 ----
        var rawDates = records.map(function (r) { return r.date; });
        var firstDate = rawDates[0].slice(0, 10);
        var sameDay = rawDates.every(function (d) { return d.slice(0, 10) === firstDate; });
        var dates = rawDates.map(function (d) {
            if (sameDay) {
                var m = d.match(/T(\d{2}:\d{2})/);
                return m ? m[1] : d;
            }
            return d.slice(0, 10);
        });

        // ---- 提取数据列 ----
        var closeLine = records.map(function (r) { return r.close; });
        var ohlc = records.map(function (r) { return [r.open, r.close, r.low, r.high]; });
        var volumes = records.map(function (r) { return [r.volume || 0, r.close >= r.open ? 1 : -1]; });
        var volData = volumes.map(function (v) { return v[0]; });
        var bbUpper = records.map(function (r) { return r.boll_upper; });
        var bbMiddle = records.map(function (r) { return r.boll_middle; });
        var bbLower = records.map(function (r) { return r.boll_lower; });
        var dcHigh20 = records.map(function (r) { return r.dc_high_20; });
        var dcLow20 = records.map(function (r) { return r.dc_low_20; });
        var ma5 = records.map(function (r) { return r.ma5; });
        var ma10 = records.map(function (r) { return r.ma10; });

        var hasVolume = volumes.some(function (v) { return v[0] > 0; });

        // ---- 共享系列：MA20 / 布林中轨（同一条线，两组共用） ----
        var ma20Series = {
            name: "MA20", type: "line", data: bbMiddle,
            lineStyle: { color: "#ffd54f", width: 1.5 }, symbol: "none",
            xAxisIndex: 0, yAxisIndex: 0,
        };

        // ---- 构建各分组的 series 定义 ----
        cachedGroups.price = [
            {
                name: "走势线", type: "line", data: closeLine,
                lineStyle: { color: "#e0e6ed", width: 1.5 }, symbol: "none",
                xAxisIndex: 0, yAxisIndex: 0,
            },
        ];

        cachedGroups.ma = [
            { name: "MA5", type: "line", data: ma5, lineStyle: { color: "#ffb74d", width: 1.5 }, symbol: "none", xAxisIndex: 0, yAxisIndex: 0 },
            { name: "MA10", type: "line", data: ma10, lineStyle: { color: "#ce93d8", width: 1.5 }, symbol: "none", xAxisIndex: 0, yAxisIndex: 0 },
            ma20Series,
        ];

        cachedGroups.candlestick = [
            {
                name: "K线", type: "candlestick", data: ohlc,
                itemStyle: { color: "#4caf50", color0: "#ef5350", borderColor: "#4caf50", borderColor0: "#ef5350" },
                xAxisIndex: 0, yAxisIndex: 0,
            },
        ];
        if (hasVolume) {
            cachedGroups.candlestick.push({
                name: "成交量", type: "bar", data: volData,
                itemStyle: {
                    color: function (params) {
                        return volumes[params.dataIndex][1] > 0 ? "#4caf50" : "#ef5350";
                    },
                },
                xAxisIndex: 1, yAxisIndex: 1,
            });
        }

        cachedGroups.bollinger = [
            ma20Series,  // 布林中轨 = MA20，即使均线组关闭也会显示
            {
                name: "布林上轨", type: "line", data: bbUpper,
                lineStyle: { color: "rgba(239,83,80,0.6)", width: 1, type: "dashed" }, symbol: "none",
                xAxisIndex: 0, yAxisIndex: 0,
            },
            {
                name: "布林下轨", type: "line", data: bbLower,
                lineStyle: { color: "rgba(76,175,80,0.6)", width: 1, type: "dashed" }, symbol: "none",
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: "rgba(79,195,247,0.05)" },
                        { offset: 1, color: "rgba(79,195,247,0.02)" },
                    ]),
                },
                xAxisIndex: 0, yAxisIndex: 0,
            },
        ];

        cachedGroups.donchian = [
            { name: "唐奇安上轨(20)", type: "line", data: dcHigh20, lineStyle: { color: "rgba(79,195,247,0.5)", width: 1 }, symbol: "none", xAxisIndex: 0, yAxisIndex: 0 },
            { name: "唐奇安下轨(20)", type: "line", data: dcLow20, lineStyle: { color: "rgba(79,195,247,0.5)", width: 1 }, symbol: "none", xAxisIndex: 0, yAxisIndex: 0 },
        ];

        // ---- 缓存基础配置 ----
        cachedBaseOption = {
            backgroundColor: "#0f1923",
            animation: true,
            tooltip: {
                trigger: "axis",
                axisPointer: { type: "cross" },
                backgroundColor: "rgba(26,39,54,0.95)",
                borderColor: "#2a3a4a",
                textStyle: { color: "#e0e6ed", fontSize: 12 },
                formatter: function (params) {
                    if (!params || params.length === 0) return "";
                    var d = params[0].axisValue;
                    var html = "<strong>" + d + "</strong><br/>";
                    params.forEach(function (p) {
                        var name = p.seriesName;
                        if (name === "K线") {
                            var vals = p.data;
                            html += "开:" + vals[1] + " 收:" + vals[2] + " 低:" + vals[3] + " 高:" + vals[4] + "<br/>";
                        } else if (name === "走势线") {
                            html += "收盘:" + p.data + "<br/>";
                        } else if (name === "成交量") {
                            // 不显示在 tooltip
                        } else {
                            html += name + ":" + p.data + "<br/>";
                        }
                    });
                    return html;
                },
            },
            grid: hasVolume
                ? [
                    { left: "8%", right: "6%", top: "6%", height: "62%" },
                    { left: "8%", right: "6%", top: "76%", height: "16%" },
                ]
                : [{ left: "8%", right: "6%", top: "6%", height: "88%" }],
            xAxis: hasVolume
                ? [
                    { type: "category", data: dates, gridIndex: 0, axisLabel: { show: false } },
                    { type: "category", data: dates, gridIndex: 1, axisLabel: { color: "#8899aa", fontSize: 11, rotate: 30 } },
                ]
                : [{ type: "category", data: dates, axisLabel: { color: "#8899aa", fontSize: 11, rotate: 30 } }],
            yAxis: hasVolume
                ? [
                    { type: "value", gridIndex: 0, scale: true, splitLine: { lineStyle: { color: "#1a2736" } }, axisLabel: { color: "#8899aa" } },
                    { type: "value", gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
                ]
                : [{ type: "value", scale: true, splitLine: { lineStyle: { color: "#1a2736" } }, axisLabel: { color: "#8899aa" } }],
        };

        // ---- 首次渲染 ----
        applyVisibility();
    }

    window.renderChart = renderChart;
    window.toggleGroup = toggleGroup;
})();
