import asyncio
import json
import logging
from pathlib import Path

import httpx

from config import settings
from core.url_parser import DESKTOP_UA, STEALTH_SCRIPT, parse_share_input

logger = logging.getLogger(__name__)

_DETAIL_API_PATH = "/aweme/v1/web/aweme/detail/"
_DETAIL_TIMEOUT = 15.0


async def _create_browser_context(playwright):
    """创建带反检测的浏览器上下文"""
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--headless=new"],
    )
    context = await browser.new_context(
        user_agent=DESKTOP_UA,
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    await context.add_init_script(STEALTH_SCRIPT)
    return browser, context


async def _warm_up_cookies(context):
    """访问首页获取 cookies，绕过反爬"""
    page = await context.new_page()
    try:
        await page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass
    await page.close()


def _parse_aweme_detail(detail: dict) -> dict:
    """解析 aweme_detail 结构为统一格式"""
    video = detail.get("video", {})
    play_addr = video.get("play_addr", {})
    url_list = play_addr.get("url_list", [])
    cover = video.get("cover", {})
    cover_list = cover.get("url_list", [])
    stats = detail.get("statistics", {})
    author = detail.get("author", {})
    music = detail.get("music", {})
    text_extra = detail.get("text_extra", [])

    video_url = url_list[0] if url_list else None
    hashtags = [t.get("hashtag_name", "") for t in text_extra if t.get("type") == 1 and t.get("hashtag_name")]

    return {
        "aweme_id": str(detail.get("aweme_id", "")),
        "title": detail.get("desc", ""),
        "author": author.get("nickname", ""),
        "author_id": str(author.get("uid", "")),
        "sec_uid": author.get("sec_uid", ""),
        "duration": video.get("duration", 0) // 1000 if video.get("duration") else None,
        "video_url": video_url,
        "share_url": f"https://www.douyin.com/video/{detail.get('aweme_id', '')}",
        "thumbnail": cover_list[0] if cover_list else None,
        "like_count": stats.get("digg_count"),
        "comment_count": stats.get("comment_count"),
        "create_time": detail.get("create_time", 0),
        "music_title": music.get("title", ""),
        "music_author": music.get("author", ""),
        "hashtags": hashtags,
    }


async def _extract_video_info(page, aweme_id: str) -> dict:
    """在已打开的页面上拦截 API 响应提取视频信息，用 Event 替代硬等待"""
    detail_data = {}
    detail_event = asyncio.Event()

    async def on_response(response):
        nonlocal detail_data
        if response.status != 200:
            return
        if _DETAIL_API_PATH not in response.url:
            return
        if aweme_id not in response.url:
            return
        try:
            text = await response.text()
            body = json.loads(text)
            detail = body.get("aweme_detail")
            if detail:
                detail_data = _parse_aweme_detail(detail)
                detail_event.set()
        except Exception:
            pass

    page.on("response", on_response)
    await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="commit", timeout=45000)

    # 等待 API 响应，最长 _DETAIL_TIMEOUT 秒
    try:
        await asyncio.wait_for(detail_event.wait(), timeout=_DETAIL_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("API 响应超时，尝试页面兜底提取")

    # 兜底：如果 API 拦截失败，尝试从页面提取
    if not detail_data:
        title = (await page.title()).replace(" - 抖音", "")
        detail_data = {
            "aweme_id": aweme_id,
            "title": title,
            "author": "",
            "duration": None,
            "video_url": None,
            "thumbnail": None,
            "like_count": None,
            "comment_count": None,
        }

    if not detail_data.get("aweme_id"):
        detail_data["aweme_id"] = aweme_id

    return detail_data


async def get_video_info_playwright(url: str) -> dict:
    """用 Playwright 从抖音页面提取视频信息"""
    from playwright.async_api import async_playwright

    aweme_id = await parse_share_input(url)

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        await _warm_up_cookies(context)
        page = await context.new_page()
        detail_data = await _extract_video_info(page, aweme_id)
        await browser.close()

    return detail_data


async def get_video_info(url: str) -> dict:
    """获取视频元信息（标题、无水印下载地址等），不下载"""
    return await get_video_info_playwright(url)


async def download_video_playwright(
    url: str,
    output_dir: str = "./downloads",
    on_progress=None,
    output_file: str | None = None,
) -> tuple[str, dict]:
    """下载无水印视频，返回 (文件路径, 视频信息)

    复用同一个浏览器生命周期：info 阶段拿到下载链接后直接下载，不再二次启动。
    on_progress: 可选回调 (downloaded_bytes, total_bytes|None)
    output_file: 可选，指定完整输出文件路径（优先于 output_dir + aweme_id）
    """
    from playwright.async_api import async_playwright

    aweme_id = await parse_share_input(url)

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        await _warm_up_cookies(context)
        page = await context.new_page()

        info = await _extract_video_info(page, aweme_id)
        await browser.close()

    video_url = info.get("video_url")
    if not video_url:
        raise ValueError("无法获取视频下载地址，请检查链接是否有效")

    if output_file:
        file_path = Path(output_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        aweme_id = info.get("aweme_id", "unknown")
        file_path = Path(output_dir) / f"{aweme_id}.mp4"

    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.douyin.com/",
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async with client.stream("GET", video_url, headers=headers, timeout=120.0) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0)) or None
            downloaded = 0
            with open(file_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total)

    return str(file_path), info


def download_video(
    url: str,
    output_dir: str = "./downloads",
    on_progress=None,
    output_file: str | None = None,
) -> tuple[str, dict]:
    """下载无水印视频，返回 (文件路径, 视频信息)（同步包装，仅 CLI 用）"""
    return asyncio.run(download_video_playwright(url, output_dir, on_progress=on_progress, output_file=output_file))


def get_video_info_sync(url: str) -> dict:
    """同步版本的 get_video_info"""
    return asyncio.run(get_video_info_playwright(url))
