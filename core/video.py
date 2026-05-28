import asyncio
import json
import re
from pathlib import Path

import httpx

from config import settings

_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
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


def _extract_aweme_id(url: str) -> str:
    """从 URL 中提取 aweme_id"""
    for pattern in [r"/video/(\d+)", r"modal_id=(\d+)", r"/note/(\d+)"]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"无法从链接提取视频ID: {url}")


async def _parse_input(text: str) -> str:
    """解析用户输入（分享口令/短链/长链），返回 aweme_id"""
    url = _extract_url_from_text(text)
    url = await _resolve_short_url(url)
    return _extract_aweme_id(url)


async def _create_browser_context(playwright):
    """创建带反检测的浏览器上下文"""
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--headless=new"],
    )
    context = await browser.new_context(
        user_agent=_DESKTOP_UA,
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    await context.add_init_script(_STEALTH_SCRIPT)
    return browser, context


async def _warm_up_cookies(context):
    """访问首页获取 cookies，绕过反爬"""
    page = await context.new_page()
    try:
        await page.goto("https://www.douyin.com/jingxuan", wait_until="commit", timeout=20000)
        await asyncio.sleep(3)
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

    video_url = url_list[0] if url_list else None

    return {
        "aweme_id": str(detail.get("aweme_id", "")),
        "title": detail.get("desc", ""),
        "author": detail.get("author", {}).get("nickname", ""),
        "duration": video.get("duration", 0) // 1000 if video.get("duration") else None,
        "video_url": video_url,
        "thumbnail": cover_list[0] if cover_list else None,
        "like_count": stats.get("digg_count"),
        "comment_count": stats.get("comment_count"),
    }


async def get_video_info_playwright(url: str) -> dict:
    """用 Playwright 从抖音页面提取视频信息"""
    from playwright.async_api import async_playwright

    aweme_id = await _parse_input(url)

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        await _warm_up_cookies(context)
        page = await context.new_page()

        # 拦截 detail API 响应
        detail_data = {}

        async def on_response(response):
            nonlocal detail_data
            resp_url = response.url
            if response.status != 200:
                return
            if "/aweme/v1/web/aweme/detail/" not in resp_url:
                return
            if aweme_id not in resp_url:
                return
            try:
                text = await response.text()
                body = json.loads(text)
                detail = body.get("aweme_detail")
                if detail:
                    detail_data = _parse_aweme_detail(detail)
            except Exception:
                pass

        page.on("response", on_response)

        await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="commit", timeout=45000)
        await asyncio.sleep(10)

        # 兜底：如果 API 拦截失败，尝试从页面提取
        if not detail_data:
            # 尝试从 video 标签获取
            video_src = await page.evaluate(
                """
                () => {
                    const v = document.querySelector('video');
                    return v ? (v.src || v.currentSrc) : null;
                }
                """
            )
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
            # blob: URL 无法直接下载，需要从 API 获取

        await browser.close()

    if not detail_data.get("aweme_id"):
        detail_data["aweme_id"] = aweme_id

    return detail_data


async def get_video_info(url: str) -> dict:
    """获取视频元信息（标题、无水印下载地址等），不下载"""
    return await get_video_info_playwright(url)


async def download_video_playwright(url: str, output_dir: str = "./downloads") -> tuple[str, dict]:
    """用 Playwright 下载无水印视频，返回 (文件路径, 视频信息)"""
    import httpx

    info = await get_video_info_playwright(url)
    video_url = info.get("video_url")

    if not video_url:
        raise ValueError("无法获取视频下载地址，请检查链接是否有效")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    aweme_id = info.get("aweme_id", "unknown")
    file_path = Path(output_dir) / f"{aweme_id}.mp4"

    headers = {
        "User-Agent": _DESKTOP_UA,
        "Referer": "https://www.douyin.com/",
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(video_url, headers=headers, timeout=120.0)
        resp.raise_for_status()
        file_path.write_bytes(resp.content)

    return str(file_path), info


def download_video(url: str, output_dir: str = "./downloads") -> tuple[str, dict]:
    """下载无水印视频，返回 (文件路径, 视频信息)（同步包装，仅 CLI 用）"""
    return asyncio.run(download_video_playwright(url, output_dir))


def get_video_info_sync(url: str) -> dict:
    """同步版本的 get_video_info"""
    return asyncio.run(get_video_info_playwright(url))
