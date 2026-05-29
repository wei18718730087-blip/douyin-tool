import asyncio
import logging
from pathlib import Path

import httpx

from core.comments import _parse_comment_item
from core.url_parser import DESKTOP_UA, STEALTH_SCRIPT, parse_share_input
from core.video import _create_browser_context, _extract_video_info, _warm_up_cookies

logger = logging.getLogger(__name__)


async def _download_and_comments_playwright(
    url: str,
    output_dir: str = "./downloads",
    max_comments: int = 50,
    output_file: str | None = None,
) -> tuple[str, dict, list[dict]]:
    """一次启动浏览器，同时完成视频下载和评论抓取"""
    from playwright.async_api import async_playwright

    aweme_id = await parse_share_input(url)

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        await _warm_up_cookies(context)

        # ── 视频信息 ──
        page = await context.new_page()
        info = await _extract_video_info(page, aweme_id)

        video_url = info.get("video_url")
        if not video_url:
            await browser.close()
            raise ValueError("无法获取视频下载地址，请检查链接是否有效")

        # ── 评论抓取（同页面上下文）──
        collected: list[dict] = []
        seen_cids: set[str] = set()

        try:
            await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)

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
        except Exception as e:
            logger.warning(f"评论抓取出错（不影响下载）: {e}")

        await browser.close()

    # ── 下载视频 ──
    if output_file:
        file_path = Path(output_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        file_path = Path(output_dir) / f"{info.get('aweme_id', 'unknown')}.mp4"

    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.douyin.com/",
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async with client.stream("GET", video_url, headers=headers, timeout=120.0) as resp:
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

    collected.sort(key=lambda c: c.get("digg_count", 0), reverse=True)
    return str(file_path), info, collected[:max_comments]


def download_and_comments(
    url: str,
    output_dir: str = "./downloads",
    max_comments: int = 50,
    output_file: str | None = None,
) -> tuple[str, dict, list[dict]]:
    """同步版本（CLI 用）"""
    return asyncio.run(
        _download_and_comments_playwright(url, output_dir=output_dir, max_comments=max_comments, output_file=output_file)
    )
