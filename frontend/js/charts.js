/** ECharts 图表渲染：K线图 + 布林带 + 唐奇安通道 + 成交量 */
(function () {
    "use strict";

    let chartInstance = null;

    /** 初始化或获取 ECharts 实例 */
    function getChart() {
        const dom = document.getElementById("mainChart");
        if (!dom) return null;
        if (chartInstance) {
            chartInstance.resize();
            return chartInstance;
        }
        chartInstance = echarts.init(dom, "dark");
        window.addEventListener("resize", () => chartInstance?.resize());
        return chartInstance;
    }

    /** 主渲染函数 */
    function renderChart(data) {
        const chart = getChart();
        if (!chart) return;

        const records = data.data || [];
        if (records.length === 0) {
            chart.setOption({ title: { text: "暂无数据", left: "center", top: "center" } });
            return;
        }

        // 准备各系列数据
        const dates = records.map((r) => r.date);
        const ohlc = records.map((r) => [r.open, r.close, r.low, r.high]);
        const volumes = records.map((r) => [r.volume || 0, r.close >= r.open ? 1 : -1]);
        const bbUpper = records.map((r) => r.boll_upper);
        const bbMiddle = records.map((r) => r.boll_middle);
        const bbLower = records.map((r) => r.boll_lower);
        const dcHigh20 = records.map((r) => r.dc_high_20);
        const dcLow20 = records.map((r) => r.dc_low_20);

        // 判断是否显示成交量（如果全为0则隐藏）
        const hasVolume = volumes.some((v) => v[0] > 0);

        const option = {
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
                    const d = params[0].axisValue;
                    let html = `<strong>${d}</strong><br/>`;
                    // 找 OHLC
                    const ohlcItem = params.find((p) => p.seriesName === "K线");
                    if (ohlcItem) {
                        const vals = ohlcItem.data;
                        html += `开: ${vals[1]}<br/>收: ${vals[2]}<br/>低: ${vals[3]}<br/>高: ${vals[4]}<br/>`;
                    }
                    const bbU = params.find((p) => p.seriesName === "布林上轨");
                    const bbM = params.find((p) => p.seriesName === "布林中轨");
                    const bbL = params.find((p) => p.seriesName === "布林下轨");
                    if (bbU && bbU.data != null) html += `布林上轨: ${bbU.data}<br/>`;
                    if (bbM && bbM.data != null) html += `布林中轨: ${bbM.data}<br/>`;
                    if (bbL && bbL.data != null) html += `布林下轨: ${bbL.data}<br/>`;
                    const dcH = params.find((p) => p.seriesName === "唐奇安上轨(20)");
                    const dcL = params.find((p) => p.seriesName === "唐奇安下轨(20)");
                    if (dcH && dcH.data != null) html += `唐奇安上轨: ${dcH.data}<br/>`;
                    if (dcL && dcL.data != null) html += `唐奇安下轨: ${dcL.data}<br/>`;
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
            series: [
                // 布林带（先绘制，在 K 线下方）
                {
                    name: "布林上轨",
                    type: "line",
                    data: bbUpper,
                    lineStyle: { color: "rgba(239,83,80,0.4)", width: 1, type: "dashed" },
                    symbol: "none",
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                },
                {
                    name: "布林中轨",
                    type: "line",
                    data: bbMiddle,
                    lineStyle: { color: "rgba(255,183,77,0.5)", width: 1 },
                    symbol: "none",
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                },
                {
                    name: "布林下轨",
                    type: "line",
                    data: bbLower,
                    lineStyle: { color: "rgba(76,175,80,0.4)", width: 1, type: "dashed" },
                    symbol: "none",
                    areaStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            { offset: 0, color: "rgba(79,195,247,0.05)" },
                            { offset: 1, color: "rgba(79,195,247,0.02)" },
                        ]),
                    },
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                },
                // 唐奇安通道
                {
                    name: "唐奇安上轨(20)",
                    type: "line",
                    data: dcHigh20,
                    lineStyle: { color: "rgba(79,195,247,0.35)", width: 1 },
                    symbol: "none",
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                },
                {
                    name: "唐奇安下轨(20)",
                    type: "line",
                    data: dcLow20,
                    lineStyle: { color: "rgba(79,195,247,0.35)", width: 1 },
                    symbol: "none",
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                },
                // K 线
                {
                    name: "K线",
                    type: "candlestick",
                    data: ohlc,
                    itemStyle: {
                        color: "#4caf50",
                        color0: "#ef5350",
                        borderColor: "#4caf50",
                        borderColor0: "#ef5350",
                    },
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                },
            ],
        };

        // 如果有成交量数据，添加到 series
        if (hasVolume) {
            option.series.push({
                name: "成交量",
                type: "bar",
                data: volumes.map((v) => v[0]),
                xAxisIndex: 1,
                yAxisIndex: 1,
                itemStyle: {
                    color: function (params) {
                        return volumes[params.dataIndex][1] > 0 ? "#4caf50" : "#ef5350";
                    },
                },
            });
        }

        chart.setOption(option, true);
    }

    window.renderChart = renderChart;
})();
