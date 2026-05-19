"""API 并发压力测试脚本。

测试改进后的异步并发能力，排除 RAG 接口（避免触发 LLM 限流）。

用法：
    python stress_test.py
    python stress_test.py --url http://localhost:8000 --concurrency 5,10,20 --requests 20
"""

import asyncio
import json
import statistics
import time
from argparse import ArgumentParser
from dataclasses import dataclass, field

import httpx


@dataclass
class RequestResult:
    """单次请求结果。"""
    status: int
    elapsed: float          # 秒
    body_size: int | None = None
    error: str | None = None


@dataclass
class BenchmarkResult:
    """单端点单并发级别的汇总结果。"""
    endpoint: str
    method: str
    concurrency: int
    total: int
    success: int
    fail: int
    elapsed_min: float
    elapsed_max: float
    elapsed_avg: float
    elapsed_p50: float
    elapsed_p95: float
    elapsed_p99: float
    throughput: float       # req/s
    total_duration: float   # 秒
    results: list[RequestResult] = field(default_factory=list)


# ---- 测试用例定义 ----
TEST_CASES: list[dict] = [
    {
        "name": "health",
        "method": "GET",
        "url": "/api/health",
        "json": None,
        "params": None,
    },
    {
        "name": "indices_list",
        "method": "GET",
        "url": "/api/indices",
        "json": None,
        "params": None,
    },
    {
        "name": "index_analysis",
        "method": "GET",
        "url": "/api/indices/%5EGSPC/analysis",  # ^GSPC URL-encoded
        "json": None,
        "params": {"start_date": "2026-04-01", "end_date": "2026-05-19"},
    },
    {
        "name": "predict",
        "method": "POST",
        "url": "/api/predict",
        "json": {"keywords": ["nasdaq", "s&p500"], "limit": 10, "threshold": 100000},
        "params": None,
    },
    {
        "name": "guardian_news",
        "method": "POST",
        "url": "/api/guardian_news",
        "json": None,
        "params": None,
    },
    {
        "name": "market_status",
        "method": "GET",
        "url": "/api/market/status",
        "json": None,
        "params": None,
    },
]


async def _single_request(
    client: httpx.AsyncClient,
    base_url: str,
    case: dict,
    timeout: float,
) -> RequestResult:
    """发送单次请求并计时。"""
    url = f"{base_url}{case['url']}"
    start = time.perf_counter()
    try:
        if case["method"] == "GET":
            resp = await client.get(url, params=case.get("params"), timeout=timeout)
        else:
            resp = await client.post(
                url,
                json=case.get("json"),
                params=case.get("params"),
                timeout=timeout,
            )
        elapsed = time.perf_counter() - start
        return RequestResult(
            status=resp.status_code,
            elapsed=elapsed,
            body_size=len(resp.content),
        )
    except Exception as e:
        elapsed = time.perf_counter() - start
        return RequestResult(status=0, elapsed=elapsed, error=str(e))


async def _run_batch(
    case: dict,
    base_url: str,
    concurrency: int,
    n_requests: int,
    timeout: float,
) -> BenchmarkResult:
    """以指定并发数执行一批请求。"""
    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(concurrency)

        async def _bounded_request() -> RequestResult:
            async with sem:
                return await _single_request(client, base_url, case, timeout)

        start = time.perf_counter()
        tasks = [_bounded_request() for _ in range(n_requests)]
        results = await asyncio.gather(*tasks)
        total_duration = time.perf_counter() - start

    successes = [r for r in results if r.status > 0 and r.status < 500]
    failures = [r for r in results if r.status == 0 or r.status >= 500]

    if successes:
        times = sorted(r.elapsed for r in successes)
        p50_idx = int(len(times) * 0.50)
        p95_idx = int(len(times) * 0.95)
        p99_idx = int(len(times) * 0.99)
        elapsed_min = times[0]
        elapsed_max = times[-1]
        elapsed_avg = statistics.mean(times)
        elapsed_p50 = times[min(p50_idx, len(times) - 1)]
        elapsed_p95 = times[min(p95_idx, len(times) - 1)]
        elapsed_p99 = times[min(p99_idx, len(times) - 1)]
        throughput = len(results) / total_duration
    else:
        elapsed_min = elapsed_max = elapsed_avg = elapsed_p50 = elapsed_p95 = elapsed_p99 = 0.0
        throughput = 0.0

    return BenchmarkResult(
        endpoint=case["name"],
        method=case["method"],
        concurrency=concurrency,
        total=len(results),
        success=len(successes),
        fail=len(failures),
        elapsed_min=elapsed_min,
        elapsed_max=elapsed_max,
        elapsed_avg=elapsed_avg,
        elapsed_p50=elapsed_p50,
        elapsed_p95=elapsed_p95,
        elapsed_p99=elapsed_p99,
        throughput=throughput,
        total_duration=total_duration,
        results=results,
    )


def _print_header(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def _print_result(r: BenchmarkResult) -> None:
    status_bar = f"{'#' * r.success}{'.' * r.fail}" if r.success + r.fail <= 50 else ""
    print(
        f"\n  [{r.method}] {r.endpoint}  (并发={r.concurrency:>3}, 请求={r.total})"
    )
    print(f"    成功: {r.success}  失败: {r.fail}  耗时: {r.total_duration:.2f}s  吞吐: {r.throughput:.1f} req/s")
    if r.success > 0:
        print(
            f"    响应时间 | min: {r.elapsed_min:.3f}s  max: {r.elapsed_max:.3f}s  "
            f"avg: {r.elapsed_avg:.3f}s  p50: {r.elapsed_p50:.3f}s  "
            f"p95: {r.elapsed_p95:.3f}s  p99: {r.elapsed_p99:.3f}s"
        )
    if r.fail > 0:
        errors = set(rr.error for rr in r.results if rr.error)
        for e in errors:
            print(f"    错误: {e[:100]}")
    if status_bar:
        print(f"    [{status_bar}]")


def _print_summary_table(results: list[BenchmarkResult]) -> None:
    _print_header("汇总对比")

    # 按 endpoint 分组，每个并发级别一行
    endpoints = sorted(set(r.endpoint for r in results))
    concurrency_levels = sorted(set(r.concurrency for r in results))

    print(f"\n  {'Endpoint':<25} {'并发':>4}  {'成功':>5} {'失败':>4}  "
          f"{'avg':>8}  {'p50':>8}  {'p95':>8}  {'吞吐':>8}")
    print(f"  {'-'*25} {'-'*4}  {'-'*5} {'-'*4}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")

    for ep in endpoints:
        for c in concurrency_levels:
            matches = [r for r in results if r.endpoint == ep and r.concurrency == c]
            if not matches:
                continue
            r = matches[0]
            print(
                f"  {ep:<25} {r.concurrency:>4}  "
                f"{r.success:>5} {r.fail:>4}  "
                f"{r.elapsed_avg:>7.3f}s {r.elapsed_p50:>7.3f}s {r.elapsed_p95:>7.3f}s "
                f"{r.throughput:>7.1f}/s"
            )


async def main(
    base_url: str,
    concurrency_levels: list[int],
    n_requests: int,
    timeout: float,
) -> None:
    _print_header("压力测试配置")
    print(f"  服务器: {base_url}")
    print(f"  并发级别: {concurrency_levels}")
    print(f"  每端点每级别请求数: {n_requests}")
    print(f"  请求超时: {timeout}s")
    print(f"  测试接口数: {len(TEST_CASES)}")
    print(f"  预计总请求: {len(TEST_CASES) * len(concurrency_levels) * n_requests}")

    # 预热：先发一次请求确保服务可用
    print(f"\n  预热中...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{base_url}/api/health", timeout=10)
            print(f"  服务器响应: {resp.status_code} {resp.json()}")
    except Exception as e:
        print(f"  无法连接服务器: {e}")
        return

    all_results: list[BenchmarkResult] = []

    for case in TEST_CASES:
        _print_header(f"测试: [{case['method']}] {case['name']}")

        for c in concurrency_levels:
            result = await _run_batch(case, base_url, c, n_requests, timeout)
            all_results.append(result)
            _print_result(result)

    _print_summary_table(all_results)

    # 总体统计
    total_success = sum(r.success for r in all_results)
    total_fail = sum(r.fail for r in all_results)
    total_req = total_success + total_fail
    _print_header("总体统计")
    print(f"  总请求: {total_req}  成功: {total_success}  失败: {total_fail}  成功率: {total_success/max(total_req,1)*100:.1f}%")

    # 并发能力评估
    print(f"\n  并发能力评估:")
    for c in concurrency_levels:
        level_results = [r for r in all_results if r.concurrency == c]
        if level_results:
            avg_tp = statistics.mean(r.throughput for r in level_results if r.throughput > 0)
            avg_lat = statistics.mean(r.elapsed_avg for r in level_results if r.elapsed_avg > 0)
            fails = sum(r.fail for r in level_results)
            print(f"    并发={c:>3}: 平均吞吐={avg_tp:.1f} req/s, 平均延迟={avg_lat:.3f}s, 失败={fails}")


if __name__ == "__main__":
    parser = ArgumentParser(description="API 并发压力测试")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="服务器地址")
    parser.add_argument(
        "--concurrency",
        default="5,10,20",
        help="并发级别，逗号分隔（默认 5,10,20）",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=15,
        help="每个并发级别的请求总数（默认 15）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="单请求超时秒数（默认 60）",
    )
    args = parser.parse_args()

    concurrency_levels = [int(x.strip()) for x in args.concurrency.split(",")]

    asyncio.run(main(args.url, concurrency_levels, args.requests, args.timeout))
