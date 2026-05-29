import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import settings
from core.comments import fetch_comments_playwright
from core.keywords import extract_keywords
from core.video import download_video_playwright, get_video_info_playwright
from models.schemas import CommentsRequest, DownloadRequest, KeywordsRequest, VideoRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="抖音工具 - 无水印下载 & 评论抓取 & 关键词提取",
    version="0.2.0",
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/v1/video/info")
async def api_video_info(body: VideoRequest):
    """获取视频信息（不下载）"""
    try:
        info = await get_video_info_playwright(body.url)
        return {"status": "ok", **info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/video/download")
async def api_video_download(body: DownloadRequest):
    """下载无水印视频"""
    try:
        file_path, info = await download_video_playwright(body.url, body.output_dir)
        return {"status": "ok", "file_path": file_path, **info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/keywords")
async def api_keywords(body: KeywordsRequest):
    """从文本中提取高频关键词"""
    try:
        result = extract_keywords(body.texts, top_k=body.count, method=body.method)
        return {"status": "ok", "keywords": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/comments")
async def api_comments(body: CommentsRequest):
    """抓取视频评论"""
    try:
        comments = await fetch_comments_playwright(body.url, max_comments=body.max_comments)
        return {"status": "ok", "count": len(comments), "comments": comments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
