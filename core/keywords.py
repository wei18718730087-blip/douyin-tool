from collections import Counter
from pathlib import Path
from typing import Optional

import jieba
import jieba.analyse

STOPWORDS_PATH = Path(__file__).parent.parent / "stopwords.txt"


def extract_keywords(
    comments: list[str],
    top_k: int = 20,
    method: str = "mixed",
) -> list[dict]:
    """从评论列表中提取高频关键词

    Args:
        comments: 评论文本列表
        top_k: 返回前 N 个关键词
        method: 提取方法 - tfidf / textrank / freq / mixed

    Returns:
        [{ word, tfidf_score?, count? }, ...]
    """
    full_text = " ".join(comments)

    if STOPWORDS_PATH.exists():
        jieba.analyse.set_stop_words(str(STOPWORDS_PATH))

    stopwords: set[str] = set()
    if STOPWORDS_PATH.exists():
        stopwords = set(STOPWORDS_PATH.read_text().splitlines())

    results: list[dict] = []

    if method in ("tfidf", "mixed"):
        tfidf_keywords = jieba.analyse.extract_tags(
            full_text,
            topK=top_k,
            withWeight=True,
            allowPOS=("n", "v", "a", "nr", "ns"),
        )
        for word, weight in tfidf_keywords:
            results.append({"word": word, "tfidf_score": round(weight, 4)})

    if method in ("textrank", "mixed"):
        textrank_keywords = jieba.analyse.textrank(
            full_text,
            topK=top_k,
            withWeight=True,
            allowPOS=("n", "v", "a", "nr", "ns"),
        )
        if method == "textrank":
            results = [{"word": w, "tfidf_score": round(s, 4)} for w, s in textrank_keywords]
        else:
            existing_words = {r["word"] for r in results}
            for word, weight in textrank_keywords:
                if word not in existing_words:
                    results.append({"word": word, "tfidf_score": round(weight, 4)})

    if method in ("freq", "mixed"):
        words = jieba.cut(full_text)
        word_list = [w for w in words if len(w) > 1 and w not in stopwords]
        freq = Counter(word_list).most_common(top_k)

        if method == "freq":
            results = [{"word": w, "count": c} for w, c in freq]
        else:
            freq_dict = dict(freq)
            for r in results:
                r["count"] = freq_dict.get(r["word"], 0)

    return results[:top_k]
