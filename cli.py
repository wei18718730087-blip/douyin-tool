import json
import logging
import sys
from pathlib import Path

import click

from config import settings
from core.comments import fetch_comments
from core.keywords import extract_keywords
from core.video import download_video, get_video_info_sync

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )


def _json_output(data) -> None:
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _classify_error(e: Exception) -> str:
    """将异常转为用户可读的错误信息"""
    err_str = str(e).lower()
    if "timeout" in err_str or "timed out" in err_str:
        return "网络超时，请检查网络连接后重试"
    if "connection" in err_str or "resolve" in err_str:
        return "网络连接失败，请检查网络"
    if "403" in err_str or "forbidden" in err_str:
        return "被抖音反爬拦截，稍后重试或更换网络"
    if "无法获取视频下载地址" in str(e):
        return "链接无效或视频已删除"
    if "未找到有效链接" in str(e):
        return "输入中未找到有效链接，请粘贴抖音分享口令或 URL"
    if "无法从链接提取视频ID" in str(e):
        return "链接格式无法识别，支持：抖音分享口令、短链、视频页长链"
    return str(e)


def _read_urls_from_file(filepath: str) -> list[str]:
    """从文件读取 URL 列表（每行一个）"""
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


# ── 公共选项 ──────────────────────────────────────────────

class _CommonOpts:
    """Click 用的公共选项 mixin（通过 callback 注入）"""

    @staticmethod
    def add(f):
        f = click.option("-v", "--verbose", is_flag=True, help="详细日志")(f)
        f = click.option("-q", "--quiet", is_flag=True, help="静默模式，仅输出 JSON")(f)
        return f


# ── CLI ───────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
@click.option("-v", "--verbose", is_flag=True, help="详细日志")
@click.option("-q", "--quiet", is_flag=True, help="静默模式，仅输出 JSON")
@click.option("--version", is_flag=True, help="显示版本")
def main(ctx, verbose, quiet, version):
    """抖音工具 - 无水印下载 & 评论抓取 & 关键词提取"""
    _setup_logging(verbose, quiet)
    if version:
        click.echo("douyin-tool 0.1.0")
        return
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── download ──────────────────────────────────────────────

@main.command()
@click.argument("urls", nargs=-1, required=False)
@click.option("-o", "--output-dir", default=settings.output_dir, help="视频保存目录")
@click.option("-f", "--file", "url_file", type=click.Path(exists=True), help="从文件读取 URL（每行一个）")
@click.option("--info-only", is_flag=True, help="仅获取信息，不下载")
@_CommonOpts.add
def download(urls, output_dir, url_file, info_only, verbose, quiet):
    """下载无水印视频（支持批量）

    示例:
      douyin-tool download <url>
      douyin-tool download <url1> <url2> <url3>
      douyin-tool download -f urls.txt
      douyin-tool download --info-only <url>
    """
    # 收集所有 URL
    all_urls = list(urls)
    if url_file:
        all_urls.extend(_read_urls_from_file(url_file))

    if not all_urls:
        click.echo("错误: 请提供至少一个 URL（直接传参或用 -f 指定文件）", err=True)
        sys.exit(1)

    results = []
    for i, url in enumerate(all_urls, 1):
        if len(all_urls) > 1 and not quiet:
            logger.info(f"[{i}/{len(all_urls)}] 处理: {url[:60]}...")

        if info_only:
            result = _handle_info(url)
        else:
            result = _handle_download(url, output_dir, quiet)
        results.append(result)

    # 批量时输出数组，单个时输出对象
    if len(results) == 1:
        _json_output(results[0])
    else:
        _json_output({"status": "ok", "count": len(results), "results": results})


def _handle_info(url: str) -> dict:
    try:
        info = get_video_info_sync(url)
        return {"status": "ok", "url": url, **info}
    except Exception as e:
        logger.error(f"获取信息失败: {e}")
        return {"status": "error", "url": url, "error": _classify_error(e)}


def _handle_download(url: str, output_dir: str, quiet: bool) -> dict:
    try:
        if quiet:
            file_path, info = download_video(url, output_dir)
        else:
            # 带进度条
            with click.progressbar(
                length=100,
                label="下载中",
                show_eta=True,
                show_pos=True,
            ) as bar:
                last_pct = [0]

                def on_progress(downloaded, total):
                    if total:
                        pct = min(int(downloaded * 100 / total), 100)
                        bar.update(pct - last_pct[0])
                        last_pct[0] = pct

                file_path, info = download_video(url, output_dir, on_progress=on_progress)
                bar.update(100 - last_pct[0])

        return {"status": "ok", "url": url, "file": file_path, **info}
    except Exception as e:
        logger.error(f"下载失败: {e}")
        return {"status": "error", "url": url, "error": _classify_error(e)}


# ── info（保留快捷方式，等价于 download --info-only）──────

@main.command()
@click.argument("url")
@_CommonOpts.add
def info(url, verbose, quiet):
    """获取视频信息（不下载）"""
    result = _handle_info(url)
    _json_output(result)
    if result["status"] == "error":
        sys.exit(2)


# ── comments ──────────────────────────────────────────────

@main.command()
@click.argument("url")
@click.option("-n", "--max-comments", default=50, help="最大评论数量")
@_CommonOpts.add
def comments(url, max_comments, verbose, quiet):
    """抓取视频评论"""
    try:
        result = fetch_comments(url, max_comments=max_comments)
        _json_output({"status": "ok", "count": len(result), "comments": result})
    except Exception as e:
        logger.error(f"评论抓取失败: {e}")
        _json_output({"status": "error", "error": _classify_error(e)})
        sys.exit(2)


# ── keywords ──────────────────────────────────────────────

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
@_CommonOpts.add
def keywords(file, text, count, method, verbose, quiet):
    """从文本中提取高频关键词"""
    if not file and text is None:
        text = sys.stdin.read()

    try:
        if file:
            content = Path(file).read_text(encoding="utf-8")
        else:
            content = text

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        result = extract_keywords(lines, top_k=count, method=method)
        _json_output(result)
    except Exception as e:
        logger.error(f"关键词提取失败: {e}")
        _json_output({"status": "error", "error": _classify_error(e)})
        sys.exit(2)


if __name__ == "__main__":
    main()
