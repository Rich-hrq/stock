/** K线形态识别与分析（纯前端固定规则判断，不使用 AI） */
(function () {
    "use strict";

    // ===== 辅助函数 =====

    function bodyLen(r) {
        return Math.abs(r.close - r.open);
    }

    function upperShadow(r) {
        return r.high - Math.max(r.open, r.close);
    }

    function lowerShadow(r) {
        return Math.min(r.open, r.close) - r.low;
    }

    function totalRange(r) {
        return r.high - r.low;
    }

    function isBullish(r) {
        return r.close > r.open;
    }

    function isBearish(r) {
        return r.close < r.open;
    }

    /** 计算 [start, end] 区间内某字段的斜率，跳过 null/NaN */
    function slope(records, start, end, field) {
        var sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0, n = 0;
        for (var i = start; i <= end; i++) {
            var v = records[i][field];
            if (v == null || isNaN(v)) continue;
            sumX += i;
            sumY += v;
            sumXY += i * v;
            sumX2 += i * i;
            n++;
        }
        if (n < 2) return 0;
        var denom = n * sumX2 - sumX * sumX;
        return denom === 0 ? 0 : (n * sumXY - sumX * sumY) / denom;
    }

    /** 近 N 根 K 线平均实体大小 */
    function avgBody(records, endIdx, n) {
        var start = Math.max(0, endIdx - n + 1);
        var total = 0, count = 0;
        for (var i = start; i <= endIdx; i++) {
            var bl = bodyLen(records[i]);
            if (bl != null && !isNaN(bl)) {
                total += bl;
                count++;
            }
        }
        return count > 0 ? total / count : 0;
    }

    /** 判断下跌趋势：近 N 日整体方向向下 */
    function isDowntrend(records, idx, lookback) {
        lookback = lookback || 5;
        if (idx < lookback) return false;

        // 方法1：MA20 斜率
        var maSlope = slope(records, idx - lookback, idx, "boll_middle");
        if (maSlope !== 0) return maSlope < 0;

        // 方法2：收盘价斜率
        var closeSlope = slope(records, idx - lookback, idx, "close");
        if (closeSlope !== 0) return closeSlope < 0;

        // 方法3：简单比较首尾收盘价（处理近似水平走势）
        var mid = Math.floor(idx - lookback / 2);
        var firstClose = records[idx - lookback].close;
        var lastClose = records[idx].close;
        // 收盘价下跌 且 中间价更高 → 确认不是 V 型反转
        return lastClose < firstClose && records[mid].close > lastClose;
    }

    /** 判断上涨趋势 */
    function isUptrend(records, idx, lookback) {
        lookback = lookback || 5;
        if (idx < lookback) return false;

        var maSlope = slope(records, idx - lookback, idx, "boll_middle");
        if (maSlope !== 0) return maSlope > 0;

        var closeSlope = slope(records, idx - lookback, idx, "close");
        if (closeSlope !== 0) return closeSlope > 0;

        var mid = Math.floor(idx - lookback / 2);
        var firstClose = records[idx - lookback].close;
        var lastClose = records[idx].close;
        return lastClose > firstClose && records[mid].close < lastClose;
    }

    /** 实体是否偏小（相对平均实体） */
    function isSmallBody(r, avgBl) {
        return bodyLen(r) <= avgBl * 0.55;
    }

    /** 实体是否偏大 */
    function isBigBody(r, avgBl) {
        return bodyLen(r) >= avgBl * 1.2;
    }

    // ===== 12 种形态检测 =====

    /**
     * 锤子线（Hammer）—— 单根，下跌底部，看涨
     * 条件：下跌趋势；小实体（不限颜色）；下影线 ≥ 2 倍实体；上影线极短
     */
    function detectHammer(records, idx) {
        if (idx < 5) return null;
        if (!isDowntrend(records, idx)) return null;
        var r = records[idx];
        var bl = bodyLen(r);
        var ab = avgBody(records, idx, 20);
        if (bl === 0 || !isSmallBody(r, ab)) return null;
        var ls = lowerShadow(r);
        var us = upperShadow(r);
        var tr = totalRange(r);
        if (tr === 0 || ls < bl * 1.5) return null;   // 下影线至少为实体1.5倍
        if (us > tr * 0.2 && us > bl) return null;     // 上影线不可比实体还长
        var stars = ls >= bl * 3 ? 4 : ls >= bl * 2 ? 3 : 2;
        return {
            name: "锤子线",
            enName: "Hammer",
            category: "反转看涨",
            stars: stars,
            detail: formatHammerDetail(ls, bl),
        };
    }

    /**
     * 上吊线（Hanging Man）—— 单根，上涨顶部，看跌
     * 形状与锤子线完全相同，唯一区别是出现在上涨趋势中
     */
    function detectHangingMan(records, idx) {
        if (idx < 5) return null;
        if (!isUptrend(records, idx)) return null;
        var r = records[idx];
        var bl = bodyLen(r);
        var ab = avgBody(records, idx, 20);
        if (bl === 0 || !isSmallBody(r, ab)) return null;
        var ls = lowerShadow(r);
        var us = upperShadow(r);
        var tr = totalRange(r);
        if (tr === 0 || ls < bl * 1.5) return null;
        if (us > tr * 0.2 && us > bl) return null;
        var stars = ls >= bl * 3 ? 4 : ls >= bl * 2 ? 3 : 2;
        return {
            name: "上吊线",
            enName: "Hanging Man",
            category: "反转看跌",
            stars: stars,
            detail: formatHangingManDetail(ls, bl),
        };
    }

    /**
     * 十字星（Doji）—— 单根，看位置定方向
     * 条件：开 ≈ 收（实体 < 波幅的 5%）；4 种变体
     */
    function detectDoji(records, idx) {
        var r = records[idx];
        var tr = totalRange(r);
        if (tr === 0) return null;
        if (bodyLen(r) / tr > 0.15) return null;

        var ls = lowerShadow(r);
        var us = upperShadow(r);
        var variant, descExtra;

        if (ls > tr * 0.6 && us < tr * 0.05) {
            variant = "蜻蜓十字星";
            descExtra = "只有长下影线，没有上影线。盘中空方曾大幅打压但被多方全部拉回。";
        } else if (us > tr * 0.6 && ls < tr * 0.05) {
            variant = "墓碑十字星";
            descExtra = "只有长上影线，没有下影线。盘中多方曾大幅推高但被空方全部砸回。";
        } else if (ls > tr * 0.3 && us > tr * 0.3) {
            variant = "长腿十字星";
            descExtra = "上下影线都很长，市场剧烈波动但最终回到原点，多空激烈博弈。";
        } else {
            variant = "标准十字星";
            descExtra = "上下影线差不多长，多空势均力敌。";
        }

        // 判断十字星的方向含义
        var directionHint;
        if (isUptrend(records, idx)) {
            directionHint = "出现在上涨顶部，暗示多方推不动了，可能反转下跌";
        } else if (isDowntrend(records, idx)) {
            directionHint = "出现在下跌底部，暗示空方压不下去了，可能反弹上涨";
        } else {
            directionHint = "出现在趋势中段，多空僵持，趋势可能继续";
        }

        return {
            name: "十字星（" + variant + "）",
            enName: "Doji (" + variant + ")",
            category: "看位置定方向",
            stars: 2,
            detail: formatDojiDetail(variant, descExtra, directionHint),
        };
    }

    /**
     * 吞没阳线（Bullish Engulfing）—— 双根，下跌底部，看涨
     * 条件：下跌趋势；前阴后阳；阳线实体完全包住阴线实体
     */
    function detectBullishEngulfing(records, idx) {
        if (idx < 1) return null;
        if (!isDowntrend(records, idx)) return null;
        var prev = records[idx - 1];
        var curr = records[idx];
        if (!isBearish(prev) || !isBullish(curr)) return null;
        if (curr.open >= prev.close || curr.close <= prev.open) return null; // 未完全吞没
        var ab = avgBody(records, idx, 20);
        var stars = isBigBody(curr, ab) ? 5 : 4;
        return {
            name: "吞没阳线",
            enName: "Bullish Engulfing",
            category: "反转看涨",
            stars: stars,
            detail: formatEngulfingDetail(true, isBigBody(curr, ab)),
        };
    }

    /**
     * 吞没阴线（Bearish Engulfing）—— 双根，上涨顶部，看跌
     */
    function detectBearishEngulfing(records, idx) {
        if (idx < 1) return null;
        if (!isUptrend(records, idx)) return null;
        var prev = records[idx - 1];
        var curr = records[idx];
        if (!isBullish(prev) || !isBearish(curr)) return null;
        if (curr.open <= prev.close || curr.close >= prev.open) return null;
        var ab = avgBody(records, idx, 20);
        var stars = isBigBody(curr, ab) ? 5 : 4;
        return {
            name: "吞没阴线",
            enName: "Bearish Engulfing",
            category: "反转看跌",
            stars: stars,
            detail: formatEngulfingDetail(false, isBigBody(curr, ab)),
        };
    }

    /**
     * 早晨之星（Morning Star）—— 三根，下跌底部，看涨
     * 条件：下跌趋势；大阴 → 小实体 → 大阳；第三根收过第一根实体一半
     */
    function detectMorningStar(records, idx) {
        if (idx < 2) return null;
        if (!isDowntrend(records, idx - 2)) return null;
        var r1 = records[idx - 2];
        var r2 = records[idx - 1];
        var r3 = records[idx];
        var ab = avgBody(records, idx, 20);
        if (!isBearish(r1) || !isBigBody(r1, ab)) return null;
        if (!isSmallBody(r2, ab)) return null;
        if (!isBullish(r3) || !isBigBody(r3, ab)) return null;
        // 第三根收过第一根实体一半
        var r1Mid = r1.close + (r1.open - r1.close) / 2;
        if (r3.close < r1Mid) return null;

        var stars = 5;
        if (bodyLen(r2) / totalRange(r2) < 0.15) stars = 5; // 接近十字星更可靠
        return {
            name: "早晨之星",
            enName: "Morning Star",
            category: "反转看涨",
            stars: stars,
            detail: formatStarDetail(true),
        };
    }

    /**
     * 黄昏之星（Evening Star）—— 三根，上涨顶部，看跌
     */
    function detectEveningStar(records, idx) {
        if (idx < 2) return null;
        if (!isUptrend(records, idx - 2)) return null;
        var r1 = records[idx - 2];
        var r2 = records[idx - 1];
        var r3 = records[idx];
        var ab = avgBody(records, idx, 20);
        if (!isBullish(r1) || !isBigBody(r1, ab)) return null;
        if (!isSmallBody(r2, ab)) return null;
        if (!isBearish(r3) || !isBigBody(r3, ab)) return null;
        var r1Mid = r1.open + (r1.close - r1.open) / 2;
        if (r3.close > r1Mid) return null;

        var stars = 5;
        if (bodyLen(r2) / totalRange(r2) < 0.15) stars = 5;
        return {
            name: "黄昏之星",
            enName: "Evening Star",
            category: "反转看跌",
            stars: stars,
            detail: formatStarDetail(false),
        };
    }

    /**
     * 上升三法（Rising Three Methods）—— 五根，上涨途中，持续看涨
     * 大阳 → 2-4 小阴回调（不破首阳低点）→ 大阳创新高
     */
    function detectRisingThreeMethods(records, idx) {
        if (idx < 4) return null;
        // 尝试不同长度的回调段（2-4 根）
        for (var pullback = 2; pullback <= 4; pullback++) {
            var firstIdx = idx - pullback - 1;
            if (firstIdx < 0) continue;
            var r1 = records[firstIdx];
            if (!isBullish(r1)) continue;
            var ab = avgBody(records, idx, 20);
            if (!isBigBody(r1, ab)) continue;

            var valid = true;
            for (var j = firstIdx + 1; j < idx; j++) {
                var rj = records[j];
                if (!isBearish(rj)) { valid = false; break; }
                if (rj.low < r1.low) { valid = false; break; }  // 跌破首阳低点，失效
                // 回调应该是小阴线
                if (bodyLen(rj) > ab * 0.8) { valid = false; break; }
            }
            if (!valid) continue;

            var rLast = records[idx];
            if (!isBullish(rLast) || !isBigBody(rLast, ab)) continue;
            if (rLast.close <= r1.high) continue; // 未创新高

            return {
                name: "上升三法",
                enName: "Rising Three Methods",
                category: "持续看涨",
                stars: 4,
                detail: formatThreeMethodsDetail(true, pullback),
            };
        }
        return null;
    }

    /**
     * 下降三法（Falling Three Methods）—— 五根，下跌途中，持续看跌
     * 大阴 → 2-4 小阳反弹（不破首阴高点）→ 大阴创新低
     */
    function detectFallingThreeMethods(records, idx) {
        if (idx < 4) return null;
        for (var bounce = 2; bounce <= 4; bounce++) {
            var firstIdx = idx - bounce - 1;
            if (firstIdx < 0) continue;
            var r1 = records[firstIdx];
            if (!isBearish(r1)) continue;
            var ab = avgBody(records, idx, 20);
            if (!isBigBody(r1, ab)) continue;

            var valid = true;
            for (var j = firstIdx + 1; j < idx; j++) {
                var rj = records[j];
                if (!isBullish(rj)) { valid = false; break; }
                if (rj.high > r1.high) { valid = false; break; }
                if (bodyLen(rj) > ab * 0.8) { valid = false; break; }
            }
            if (!valid) continue;

            var rLast = records[idx];
            if (!isBearish(rLast) || !isBigBody(rLast, ab)) continue;
            if (rLast.close >= r1.low) continue;

            return {
                name: "下降三法",
                enName: "Falling Three Methods",
                category: "持续看跌",
                stars: 4,
                detail: formatThreeMethodsDetail(false, bounce),
            };
        }
        return null;
    }

    /**
     * 三只乌鸦（Three Black Crows）—— 三根，上涨后，看跌
     * 连续三根大阴线；每根开盘在前一根实体内；收盘接近当日最低
     */
    function detectThreeBlackCrows(records, idx) {
        if (idx < 4) return null;
        if (!isUptrend(records, idx - 3)) return null;
        var r1 = records[idx - 2];
        var r2 = records[idx - 1];
        var r3 = records[idx];
        if (!isBearish(r1) || !isBearish(r2) || !isBearish(r3)) return null;
        var ab = avgBody(records, idx, 20);
        if (!isBigBody(r1, ab) || !isBigBody(r2, ab) || !isBigBody(r3, ab)) return null;

        // 每根开盘在前一根实体内
        if (r2.open > r1.close || r2.open < r1.open) return null;
        if (r3.open > r2.close || r3.open < r2.open) return null;

        // 收盘接近当日最低
        if ((r1.close - r1.low) / totalRange(r1) > 0.35) return null;
        if ((r2.close - r2.low) / totalRange(r2) > 0.35) return null;
        if ((r3.close - r3.low) / totalRange(r3) > 0.35) return null;

        return {
            name: "三只乌鸦",
            enName: "Three Black Crows",
            category: "反转看跌",
            stars: 4,
            detail: formatCrowsSoldiersDetail(false),
        };
    }

    /**
     * 三白兵（Three White Soldiers）—— 三根，下跌后，看涨
     * 连续三根大阳线；每根开盘在前一根实体内；收盘接近当日最高
     */
    function detectThreeWhiteSoldiers(records, idx) {
        if (idx < 4) return null;
        if (!isDowntrend(records, idx - 3)) return null;
        var r1 = records[idx - 2];
        var r2 = records[idx - 1];
        var r3 = records[idx];
        if (!isBullish(r1) || !isBullish(r2) || !isBullish(r3)) return null;
        var ab = avgBody(records, idx, 20);
        if (!isBigBody(r1, ab) || !isBigBody(r2, ab) || !isBigBody(r3, ab)) return null;

        if (r2.open < r1.open || r2.open > r1.close) return null;
        if (r3.open < r2.open || r3.open > r2.close) return null;

        // 收盘接近当日最高
        if ((r1.high - r1.close) / totalRange(r1) > 0.35) return null;
        if ((r2.high - r2.close) / totalRange(r2) > 0.35) return null;
        if ((r3.high - r3.close) / totalRange(r3) > 0.35) return null;

        // 检查第三根是否动能衰减
        var extra = "";
        if (bodyLen(r3) < bodyLen(r2) * 0.7 && bodyLen(r2) < bodyLen(r1) * 0.7) {
            extra = "\n⚠️ 注意：三根阳线实体逐步缩小，属于“力竭型”三白兵，后续上涨空间可能有限。";
        }

        return {
            name: "三白兵",
            enName: "Three White Soldiers",
            category: "反转看涨",
            stars: 4,
            detail: formatCrowsSoldiersDetail(true) + extra,
        };
    }

    /**
     * 岛型反转（Island Reversal）—— 多根，顶部/底部，反转
     * 顶部：跳空上涨 → 高位盘整 → 跳空下跌
     * 底部：跳空下跌 → 低位盘整 → 跳空上涨
     */
    function detectIslandReversal(records, idx) {
        if (idx < 6 || idx > records.length - 3) return null;
        // 顶部岛型：寻找向上缺口（在 idx 之前某处）+ 向下缺口（在 idx 或之后）
        var topResult = detectTopIsland(records, idx);
        if (topResult) return topResult;

        var bottomResult = detectBottomIsland(records, idx);
        if (bottomResult) return bottomResult;

        return null;
    }

    function detectTopIsland(records, idx) {
        // 向上缺口: records[j].low > records[j-1].high（j 应该在 idx 前 2-5 根）
        var gapUpIdx = -1;
        for (var j = idx - 1; j >= idx - 5 && j >= 1; j--) {
            if (records[j].low > records[j - 1].high) {
                gapUpIdx = j;
                break;
            }
        }
        if (gapUpIdx < 0) return null;

        // 向下缺口: records[k].high < records[k-1].low（k 应该在 idx 或附近）
        var gapDownIdx = -1;
        for (var k = idx; k <= idx + 2 && k < records.length; k++) {
            if (records[k].high < records[k - 1].low) {
                gapDownIdx = k;
                break;
            }
        }
        if (gapDownIdx < 0) return null;

        // 岛至少有一根 K 线
        if (gapDownIdx <= gapUpIdx) return null;

        return {
            name: "岛型反转（顶部）",
            enName: "Island Reversal (Top)",
            category: "反转看跌",
            stars: 5,
            detail: formatIslandDetail("top", gapUpIdx, gapDownIdx),
        };
    }

    function detectBottomIsland(records, idx) {
        // 向下缺口: records[j].high < records[j-1].low
        var gapDownIdx = -1;
        for (var j = idx - 1; j >= idx - 5 && j >= 1; j--) {
            if (records[j].high < records[j - 1].low) {
                gapDownIdx = j;
                break;
            }
        }
        if (gapDownIdx < 0) return null;

        // 向上缺口: records[k].low > records[k-1].high
        var gapUpIdx = -1;
        for (var k = idx; k <= idx + 2 && k < records.length; k++) {
            if (records[k].low > records[k - 1].high) {
                gapUpIdx = k;
                break;
            }
        }
        if (gapUpIdx < 0) return null;
        if (gapUpIdx <= gapDownIdx) return null;

        return {
            name: "岛型反转（底部）",
            enName: "Island Reversal (Bottom)",
            category: "反转看涨",
            stars: 5,
            detail: formatIslandDetail("bottom", gapDownIdx, gapUpIdx),
        };
    }

    // ===== 讲解文案 =====

    function formatHammerDetail(ls, bl) {
        return "【形态特征】一根 K 线，实体很小（颜色不限），下影线很长（至少是实体的 2 倍），上影线几乎没有。\n" +
            "【原理】在下跌过程中，空方先把价格打得很低（形成长下影线），但多方尾盘发力把价格拉回。空方出了全力但没守住——意味着空方力量在衰竭。\n" +
            "【出现位置】必须出现在下跌趋势底部。如果在上涨趋势中出现同样形状，那叫上吊线，含义完全相反。\n" +
            "【可靠性】⭐⭐⭐（3星）—— 单根 K 线可靠性一般，需要后续确认。\n" +
            "【确认信号】次日如果是阳线（收盘价高于本日收盘），反转概率显著增加。次日若仍是阴线——可能假信号。\n" +
            "【止损建议】设在本日下影线最低点下方。\n" +
            "【增强因素】下影线越长信号越强（本日下影线是实体的 " + (ls / bl).toFixed(1) + " 倍）；出现在关键支撑位或伴随放量，可靠性翻倍。";
    }

    function formatHangingManDetail(ls, bl) {
        return "【形态特征】与锤子线完全相同——小实体、长下影线、几乎无上影线。唯一区别是位置：锤子线在底部看涨，上吊线在顶部看跌。\n" +
            "【原理】上涨过程中出现长下影线，说明盘中一次大幅下跌，虽然最后被拉回，但这次下跌说明有人在高位大量抛售。拉回来可能只是散户接盘。\n" +
            "【出现位置】必须出现在上涨趋势顶部。长期上涨后的高位出现时最危险。\n" +
            "【可靠性】⭐⭐⭐（3星）—— 单根 K 线，需要确认。\n" +
            "【确认信号】次日如果是阴线（收盘价低于本日收盘），反转概率增加。\n" +
            "【止损建议】做空止损设在本日最高点上方。\n" +
            "【增强因素】下影线极长（本日是实体的 " + (ls / bl).toFixed(1) + " 倍），说明盘中抛压非常大——虽然拉回来了但恐慌已经开始。";
    }

    function formatDojiDetail(variant, descExtra, directionHint) {
        return "【形态特征】" + variant + "：开盘价和收盘价几乎相同（实体极小或没有）。" + descExtra + "\n" +
            "【原理】十字星代表犹豫和僵持。多空双方打了一天谁都没赢，是一个“暂停键”。\n" +
            "【当前位置含义】" + directionHint + "。\n" +
            "【可靠性】⭐⭐（单独看 2星）/ ⭐⭐⭐⭐（结合位置和后续确认 4星）。\n" +
            "【确认信号】必须等后续 K 线确认方向。如果连续 2-3 根十字星——市场严重犹豫，突破方向确认后通常有大行情。\n" +
            "【关键价值】十字星不告诉你方向，它提醒你\"这个位置有故事\"。你要做的不是立刻交易，而是等故事讲完。";
    }

    function formatEngulfingDetail(isBullish, isBigSecond) {
        var dir = isBullish ? "看涨" : "看跌";
        var firstColor = isBullish ? "阴线" : "阳线";
        var secondColor = isBullish ? "阳线" : "阴线";
        var trendPos = isBullish ? "下跌趋势底部" : "上涨趋势顶部";
        var stopPos = isBullish ? "第二根阳线最低点下方" : "第二根阴线最高点上方";
        var extra = isBigSecond ? "\n本日第二根 K 线实体较大，信号强度更可靠。" : "";

        return "【形态特征】两根 K 线。第一根 " + firstColor + "，第二根 " + secondColor + "，" +
            "第二根实体完全包住第一根实体（开盘价更低、收盘价更高）。\n" +
            "【原理】第一根说明一方在控制局面，第二根不仅收复了失地还超过了——说明另一方打了一个漂亮的反击。这是力量转换的直接证据。\n" +
            "【出现位置】" + trendPos + "。出现在中途意义不大。\n" +
            "【可靠性】⭐⭐⭐⭐（4星）—— 两根 K 线信息量大于单根，能看到完整的“攻防转换”过程。" + extra + "\n" +
            "【确认信号】第二根实体越大越可靠；配合放量更强。\n" +
            "【止损建议】" + stopPos + "。如果只是“勉强”包住（超出就那么一两个点），可靠性打折。";
    }

    function formatStarDetail(isMorning) {
        var dir = isMorning ? "看涨" : "看跌";
        var trend = isMorning ? "下跌" : "上涨";
        var first = isMorning ? "大阴线" : "大阳线";
        var third = isMorning ? "大阳线" : "大阴线";
        var phase1 = isMorning ? "空方占据绝对优势" : "多方占据绝对优势";
        var phase2 = isMorning ? "空方势头减弱——推不动了" : "多方势头减弱——推不动了";
        var phase3 = isMorning ? "多方全面接管" : "空方全面接管";

        return "【形态特征】三根 K 线。第一根" + first + " → 第二根小实体（阴阳不限，越小越好） → 第三根" + third + "。" +
            "第三根收盘至少收回第一根实体一半以上。\n" +
            "【原理】这是一个完整的“三幕剧”：第一幕 " + phase1 + " → 第二幕 " + phase2 + " → 第三幕 " + phase3 + "。\n" +
            "【出现位置】" + trend + "趋势底部/顶部。\n" +
            "【可靠性】⭐⭐⭐⭐⭐（5星）—— K 线形态中最可靠的之一。需要三根 K 线确认，信息量最大，但最难出现。\n" +
            "【确认信号】第二根如果是十字星（开=收），可靠性更高。如果第一和第二根之间有跳空，可靠性更高。第三根成交量应明显放大。\n" +
            "【止损建议】设于第二根（“星”）的最低点下方。";
    }

    function formatThreeMethodsDetail(isRising, pullbackDays) {
        var dir = isRising ? "看涨持续" : "看跌持续";
        var trend = isRising ? "上涨" : "下跌";
        var firstCandle = isRising ? "大阳线" : "大阴线";
        var midDescr = isRising ? "小阴线（获利回吐）" : "小阳线（空头回补）";
        var lastCandle = isRising ? "大阳线" : "大阴线";
        var breakCond = isRising ? "没有跌破第一根大阳线的最低点" : "没有突破第一根大阴线的最高点";
        var confirmCond = isRising ? "收盘价高于第一根最高点（创新高）" : "收盘价低于第一根最低点（创新低）";
        var stopPos = isRising ? "中间回调段的最低点下方" : "中间反弹段的最高点上方";

        return "【形态特征】五根（或更多）K 线。第一根" + firstCandle + " → 中间 " + pullbackDays + " 根" + midDescr + "（" + breakCond + "）→ 最后一根" + lastCandle + "，" + confirmCond + "。\n" +
            "【原理】大" + firstCandle + "代表趋势方向。中间的" + midDescr + "是正常的获利回吐，回调幅度很小没有破坏趋势结构。最后一根" + lastCandle + "确认回调结束趋势继续。\n" +
            "【出现位置】" + trend + "趋势中段。\n" +
            "【可靠性】⭐⭐⭐⭐（4星）。\n" +
            "【确认信号】中间回调段成交量萎缩（卖压不大），最后一根成交量放大（主力重新入场）。中间小 K 线数量不固定，2-4 根都正常（本次检测到 " + pullbackDays + " 根）。\n" +
            "【止损建议】" + stopPos + "。如果中间回调突破了第一根的极点，形态失效。";
    }

    function formatCrowsSoldiersDetail(isSoldiers) {
        var dir = isSoldiers ? "看涨" : "看跌";
        var color = isSoldiers ? "阳线" : "阴线";
        var trendPos = isSoldiers ? "下跌趋势底部" : "上涨趋势顶部";
        var closePos = isSoldiers ? "最高" : "最低";
        var failDesc = isSoldiers
            ? "第三根阳线实体明显变小（相比前两根），说明多方动能在衰减——可能是\"力竭型\"三白兵。第三根上影线很长也说明上方压力大。"
            : "成交量逐步放大更可靠——说明越来越多的人在卖。三只乌鸦后通常还有惯性下跌，不要急着抄底。";
        var stopPos = isSoldiers ? "第一根阳线最低点下方" : "第一根阴线最高点上方";

        return "【形态特征】连续三根大" + color + "。每根开盘价在前一根实体范围内，收盘价逐步创" + (isSoldiers ? "新" : "新") + "高/低。\n" +
            "【原理】" + (isSoldiers ? "三天连续大涨" : "三天连续大跌") + "，" + (isSoldiers ? "多方" : "空方") +
            "完全控场，对手毫无还手之力。这不是偶然的一天走势，连续三天说明力量是持续的、系统性的。\n" +
            "【出现位置】" + trendPos + "。\n" +
            "【可靠性】⭐⭐⭐⭐（4星）。\n" +
            "【确认信号】" + failDesc + "每根" + color + "收盘应接近当日" + closePos + "（说明一路打到收盘没有反弹）。\n" +
            "【止损建议】" + stopPos + "。";
    }

    function formatIslandDetail(type, gap1Idx, gap2Idx) {
        var dir = type === "top" ? "看跌" : "看涨";
        var gap1 = type === "top" ? "跳空上涨（向上缺口）" : "跳空下跌（向下缺口）";
        var gap2 = type === "top" ? "跳空下跌（向下缺口）" : "跳空上涨（向上缺口）";
        var emotion = type === "top"
            ? "第一个缺口是最后的疯狂买入，第二个缺口是恐慌性抛售。从极度乐观到极度悲观的急转"
            : "第一个缺口是恐慌性抛售，第二个缺口是抄底资金涌入。从极度悲观到极度乐观的急转";
        var stopNote = type === "top" ? "如果价格重新回到\"岛\"上（缺口被回补），形态失效，立即止损。" : "";

        return "【形态特征】先" + gap1 + " → 价格在孤立区间运行 → 再" + gap2 + "。" +
            "高位/低位那段 K 线被两个缺口“隔离”了，像一座孤岛。\n" +
            "【原理】两个跳空缺口说明市场情绪发生剧烈转变。" + emotion + "——这种情绪落差通常意味着趋势已经结束。\n" +
            "【出现位置】" + (type === "top" ? "上涨趋势顶部" : "下跌趋势底部") + "。\n" +
            "【可靠性】⭐⭐⭐⭐⭐（5星）—— 所有 K 线形态中可靠性最高之一，但非常罕见（日线图上可能几个月才出现一次）。\n" +
            "【止损设置】岛型反转的止损非常明确：" + stopNote + "\n" +
            "【增强因素】缺口越大信号越强；\"岛\"上交易日越多反转后行情幅度通常越大；配合异常放量更强。";
    }

    // ===== 主检测函数 =====

    /** 检测所有形态，返回命中列表 */
    function analyzeCandlestick(records, idx) {
        var r = records[idx];
        console.log("[K线分析] 点击日期:", r.date, "| O:", r.open, "H:", r.high, "L:", r.low, "C:", r.close,
                    "| 实体:", bodyLen(r).toFixed(2), "波幅:", totalRange(r).toFixed(2),
                    "| 下影线:", lowerShadow(r).toFixed(2), "上影线:", upperShadow(r).toFixed(2),
                    "| 实体/波幅:", (bodyLen(r)/totalRange(r)*100).toFixed(1) + "%",
                    "| 跌势:", isDowntrend(records, idx), "涨势:", isUptrend(records, idx));

        var results = [];

        // 数据充足性
        var hasEnoughForMulti = idx >= 4 && records.length >= 5;

        // 单根形态（始终检测）
        var hammer = detectHammer(records, idx);
        if (hammer) results.push(hammer);

        var hangingMan = detectHangingMan(records, idx);
        if (hangingMan) results.push(hangingMan);

        var doji = detectDoji(records, idx);
        if (doji) results.push(doji);

        // 多根形态（数据充足时检测）
        if (hasEnoughForMulti) {
            var bullishEngulfing = detectBullishEngulfing(records, idx);
            if (bullishEngulfing) results.push(bullishEngulfing);

            var bearishEngulfing = detectBearishEngulfing(records, idx);
            if (bearishEngulfing) results.push(bearishEngulfing);

            var morningStar = detectMorningStar(records, idx);
            if (morningStar) results.push(morningStar);

            var eveningStar = detectEveningStar(records, idx);
            if (eveningStar) results.push(eveningStar);

            var risingThree = detectRisingThreeMethods(records, idx);
            if (risingThree) results.push(risingThree);

            var fallingThree = detectFallingThreeMethods(records, idx);
            if (fallingThree) results.push(fallingThree);

            var threeCrows = detectThreeBlackCrows(records, idx);
            if (threeCrows) results.push(threeCrows);

            var threeSoldiers = detectThreeWhiteSoldiers(records, idx);
            if (threeSoldiers) results.push(threeSoldiers);

            var island = detectIslandReversal(records, idx);
            if (island) results.push(island);
        }

        // 按可靠性星级降序排列
        results.sort(function (a, b) { return b.stars - a.stars; });

        console.log("[K线分析] 命中 " + results.length + " 个形态:", results.map(function(r) { return r.name; }).join(", ") || "(无)");

        return results;
    }

    // ===== 弹出窗口 =====

    var overlayEl = null;

    function getOverlay() {
        if (overlayEl) return overlayEl;
        overlayEl = document.getElementById("candlestickOverlay");
        return overlayEl;
    }

    function showPopup(results, dateStr) {
        var overlay = getOverlay();
        if (!overlay) return;
        var body = document.getElementById("candlestickPopupBody");
        if (!body) return;
        document.getElementById("candlestickPopupDate").textContent = dateStr;

        if (results.length === 0) {
            body.innerHTML = '<div class="pattern-empty"><p>未检测到明显的 K 线形态</p><p class="pattern-empty-hint">该日 K 线不满足 12 种常见形态的判断条件。可能是普通交易日，或者形态不够标准。</p></div>';
        } else {
            body.innerHTML = results.map(function (r) {
                return buildPatternCard(r);
            }).join("");
        }

        overlay.classList.remove("hidden");
    }

    function buildPatternCard(r) {
        var starsStr = "";
        for (var i = 0; i < 5; i++) {
            starsStr += i < r.stars ? "★" : "☆";
        }

        var catClass = "pattern-cat-neutral";
        if (r.category.indexOf("看涨") >= 0) {
            catClass = "pattern-cat-bullish";
        } else if (r.category.indexOf("看跌") >= 0) {
            catClass = "pattern-cat-bearish";
        }

        // 将 \n 转为 HTML 段落
        var detailHtml = r.detail
            .split("\n")
            .filter(function (line) { return line.trim().length > 0; })
            .map(function (line) {
                // 处理 【标题】 加粗
                line = line.replace(/【(.+?)】/g, '<strong>【$1】</strong>');
                return '<p>' + line + '</p>';
            })
            .join("");

        return '<div class="pattern-card">' +
            '<div class="pattern-card-header">' +
            '<span class="pattern-name">' + r.name + '</span>' +
            '<span class="pattern-en-name">' + r.enName + '</span>' +
            '<span class="pattern-stars" title="可靠性 ' + r.stars + '/5 星">' + starsStr + '</span>' +
            '<span class="pattern-category ' + catClass + '">' + r.category + '</span>' +
            '</div>' +
            '<div class="pattern-card-body">' + detailHtml + '</div>' +
            '</div>';
    }

    function hidePopup() {
        var overlay = getOverlay();
        if (overlay) overlay.classList.add("hidden");
    }

    function bindPopupEvents() {
        document.getElementById("candlestickOverlay")?.addEventListener("click", function (e) {
            if (e.target === this) hidePopup();
        });
        document.getElementById("candlestickPopupClose")?.addEventListener("click", hidePopup);
        document.getElementById("candlestickPopupCloseBtn")?.addEventListener("click", hidePopup);
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") hidePopup();
        });
    }

    // 初始化
    bindPopupEvents();

    // 暴露给全局
    window.analyzeCandlestick = analyzeCandlestick;
    window.showCandlestickPopup = showPopup;
    window.hideCandlestickPopup = hidePopup;
})();
