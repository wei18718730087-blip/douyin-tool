import asyncio
import logging

from core.url_parser import DESKTOP_UA, STEALTH_SCRIPT, parse_share_input

logger = logging.getLogger(__name__)


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

    aweme_id = await parse_share_input(url)

    collected: list[dict] = []
    seen_cids: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--headless=new"],
        )
        context = await browser.new_context(
            user_agent=DESKTOP_UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        await context.add_init_script(STEALTH_SCRIPT)

        # 先访问首页获取 cookies
        warmup = await context.new_page()
        try:
            await warmup.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        await warmup.close()

        # 打开视频页面（建立上下文）
        page = await context.new_page()
        await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)

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
