import json
import logging
import sys

import click

from config import settings
from core.comments import fetch_comments
from core.keywords import extract_keywords
from core.video import download_video, get_video_info_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def _json_output(data) -> None:
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


@click.group()
def main():
    """抖音工具 - 无水印下载 & 评论抓取 & 关键词提取"""
    pass


@main.command()
@click.argument("url")
def info(url: str):
    """获取视频信息（不下载）"""
    try:
        video_info = get_video_info_sync(url)
        _json_output({"status": "ok", **video_info})
    except Exception as e:
        logger.error(f"获取信息失败: {e}")
        _json_output({"status": "error", "error": str(e)})
        sys.exit(2)


@main.command()
@click.argument("url")
@click.option("-o", "--output-dir", default=settings.output_dir, help="视频保存目录")
def download(url: str, output_dir: str):
    """下载无水印视频"""
    try:
        file_path, info = download_video(url, output_dir)
        _json_output({"status": "ok", "file": file_path, **info})
    except Exception as e:
        logger.error(f"下载失败: {e}")
        _json_output({"status": "error", "error": str(e)})
        sys.exit(2)


@main.command()
@click.argument("url")
@click.option("-o", "--output-dir", default=settings.output_dir, help="视频保存目录")
def analyze(url: str, output_dir: str):
    """获取信息并下载视频"""
    result: dict = {"status": "ok"}
    try:
        file_path, video_info = download_video(url, output_dir)
        video_info["file_path"] = file_path
        result["video"] = video_info
        _json_output(result)
    except Exception as e:
        logger.error(f"分析失败: {e}")
        result["status"] = "error"
        result["error"] = str(e)
        _json_output(result)
        sys.exit(2)


@main.command()
@click.argument("url")
@click.option("-n", "--max-comments", default=50, help="最大评论数量")
def comments(url: str, max_comments: int):
    """抓取视频评论"""
    try:
        result = fetch_comments(url, max_comments=max_comments)
        _json_output({"status": "ok", "count": len(result), "comments": result})
    except Exception as e:
        logger.error(f"评论抓取失败: {e}")
        _json_output({"status": "error", "error": str(e)})
        sys.exit(2)


@main.command()
@click.option("-f", "--file", type=click.Path(exists=True), help="从文件读取文本")
@click.option("-t", "--text", help="直接传入文本")
@click.option("-n", "--count", default=20, help="关键词数量")
@click.option(
    "--method",
    default="mixed",
    type=click.Choice(["tfidf", "textrank", "freq", "mixed"]),
    help="提取方法",
)
def keywords(file: str, text: str, count: int, method: str):
    """从文本中提取高频关键词"""
    if not file and not text:
        # 从 stdin 读取
        text = sys.stdin.read()

    try:
        if file:
            from pathlib import Path
            content = Path(file).read_text(encoding="utf-8")
        else:
            content = text

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        result = extract_keywords(lines, top_k=count, method=method)
        _json_output(result)
    except Exception as e:
        logger.error(f"关键词提取失败: {e}")
        _json_output({"status": "error", "error": str(e)})
        sys.exit(2)


if __name__ == "__main__":
    main()
