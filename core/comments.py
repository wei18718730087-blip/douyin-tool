import asyncio
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}};
"""


def _extract_url_from_text(text: str) -> str:
    """从分享口令中提取 URL"""
    match = re.search(r"https?://[^\s]+", text)
    if not match:
        raise ValueError("未找到有效链接")
    return match.group(0).rstrip("/")


async def _resolve_short_url(url: str) -> str:
    """跟踪短链重定向，返回最终长链接"""
    if "v.douyin.com" not in url and "vm.douyin.com" not in url:
        return url
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(url, headers={"User-Agent": _DESKTOP_UA}, timeout=10.0)
            location = resp.headers.get("Location", "")
            if location:
                return location
    except Exception:
        pass
    return url


async def _parse_input(text: str) -> str:
    """解析用户输入（分享口令/短链/长链），返回 aweme_id"""
    url = _extract_url_from_text(text)
    url = await _resolve_short_url(url)
    for pattern in [r"/video/(\d+)", r"modal_id=(\d+)", r"/note/(\d+)"]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"无法从链接提取视频ID: {url}")


def _parse_comment_item(item: dict) -> dict:
    """从 API 响应的单条评论中提取字段"""
    user = item.get("user", {})
    return {
        "cid": str(item.get("cid", "")),
        "text": item.get("text", ""),
        "author": user.get("nickname", ""),
        "author_uid": str(user.get("uid", "")),
        "create_time": item.get("create_time", 0),
        "digg_count": item.get("digg_count", 0),
        "reply_count": item.get("reply_comment_total", 0),
    }


async def fetch_comments_playwright(
    url: str,
    max_comments: int = 50,
    max_scrolls: int = 30,
) -> list[dict]:
    """用 Playwright 抓取视频评论

    访问首页获取 cookies → 打开视频页面 → 直接调用 comment/list API 分页获取 → 返回评论列表
    """
    from playwright.async_api import async_playwright

    aweme_id = await _parse_input(url)

    collected: list[dict] = []
    seen_cids: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--headless=new"],
        )
        context = await browser.new_context(
            user_agent=_DESKTOP_UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        await context.add_init_script(_STEALTH_SCRIPT)

        # 先访问首页获取 cookies
        warmup = await context.new_page()
        try:
            await warmup.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
        except Exception:
            pass
        await warmup.close()

        # 打开视频页面（建立上下文）
        page = await context.new_page()
        await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="commit", timeout=45000)
        await asyncio.sleep(5)

        # 直接调用 comment/list API 分页获取评论
        cursor = 0
        page_count = 20
        has_more = True

        while has_more and len(collected) < max_comments:
            result = await page.evaluate(
                """async (params) => {
                    try {
                        const url = '/aweme/v1/web/comment/list/?device_platform=webapp&aid=6383&channel=channel_pc_web'
                            + '&aweme_id=' + params.aweme_id
                            + '&cursor=' + params.cursor
                            + '&count=' + params.count
                            + '&item_type=0';
                        const resp = await fetch(url, {credentials: 'include'});
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }""",
                {"aweme_id": aweme_id, "cursor": cursor, "count": page_count},
            )

            if result.get("error"):
                logger.error(f"评论 API 错误: {result['error']}")
                break

            comments = result.get("comments", [])
            if not comments:
                break

            for item in comments:
                parsed = _parse_comment_item(item)
                if parsed["cid"] not in seen_cids:
                    seen_cids.add(parsed["cid"])
                    collected.append(parsed)

            has_more = bool(result.get("has_more", 0))
            cursor = result.get("cursor", cursor + page_count)
            logger.info(f"评论分页: cursor={cursor}, 本页={len(comments)}, 已收集={len(collected)}")

            await asyncio.sleep(1)

        await browser.close()

    collected.sort(key=lambda c: c.get("digg_count", 0), reverse=True)
    return collected[:max_comments]


def fetch_comments(url: str, max_comments: int = 50) -> list[dict]:
    """同步版本（CLI 用）"""
    return asyncio.run(fetch_comments_playwright(url, max_comments))
