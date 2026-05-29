import re

import httpx

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}};
"""


def extract_url_from_text(text: str) -> str:
    """从分享口令中提取 URL"""
    match = re.search(r"https?://[^\s]+", text)
    if not match:
        raise ValueError("未找到有效链接")
    return match.group(0).rstrip("/")


async def resolve_short_url(url: str) -> str:
    """跟踪短链重定向，返回最终长链接"""
    if "v.douyin.com" not in url and "vm.douyin.com" not in url:
        return url
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(url, headers={"User-Agent": DESKTOP_UA}, timeout=10.0)
            location = resp.headers.get("Location", "")
            if location:
                return location
    except Exception:
        pass
    return url


def extract_aweme_id(url: str) -> str:
    """从 URL 中提取 aweme_id"""
    for pattern in [r"/video/(\d+)", r"modal_id=(\d+)", r"/note/(\d+)"]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"无法从链接提取视频ID: {url}")


async def parse_share_input(text: str) -> str:
    """解析用户输入（分享口令/短链/长链），返回 aweme_id"""
    url = extract_url_from_text(text)
    url = await resolve_short_url(url)
    return extract_aweme_id(url)
