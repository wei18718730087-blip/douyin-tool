import re

import httpx


async def extract_aweme_id(share_text: str) -> str:
    """从分享链接/文本中提取 aweme_id"""
    # Step 1: 从文本中提取 URL
    url_match = re.search(r"https?://[^\s]+", share_text)
    if not url_match:
        raise ValueError("未找到有效链接")
    url = url_match.group(0)

    # Step 2: 如果是短链，跟踪重定向获取长链接
    if "v.douyin.com" in url or "vm.douyin.com" in url:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                timeout=10.0,
            )
            location = resp.headers.get("Location", "")
            if location:
                url = location

    # Step 3: 从长链接提取 aweme_id
    match = re.search(r"/video/(\d+)", url)
    if not match:
        match = re.search(r"modal_id=(\d+)", url)
    if not match:
        match = re.search(r"/note/(\d+)", url)
    if not match:
        raise ValueError(f"无法从链接提取视频ID: {url}")

    return match.group(1)
