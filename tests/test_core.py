import pytest
from core.keywords import extract_keywords


class TestExtractKeywords:
    def test_tfidf_method(self):
        comments = [
            "这个视频太好看了",
            "推荐给大家看",
            "好看真的好看",
            "视频制作得真好",
        ]
        result = extract_keywords(comments, top_k=5, method="tfidf")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all("word" in r and "tfidf_score" in r for r in result)

    def test_freq_method(self):
        comments = [
            "好看好看好看",
            "推荐推荐",
            "好看",
        ]
        result = extract_keywords(comments, top_k=5, method="freq")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all("word" in r and "count" in r for r in result)
        # "好看" 出现最多
        assert result[0]["word"] == "好看"
        assert result[0]["count"] == 4

    def test_mixed_method(self):
        comments = [
            "这个视频太好看了",
            "推荐给大家看",
            "好看真的好看",
        ]
        result = extract_keywords(comments, top_k=5, method="mixed")
        assert isinstance(result, list)
        assert len(result) > 0
        # mixed 方法应同时有 tfidf_score 和 count
        assert all("word" in r for r in result)

    def test_textrank_method(self):
        comments = [
            "这个视频制作得很精美",
            "画面非常好看",
            "推荐大家看看这个视频",
        ]
        result = extract_keywords(comments, top_k=5, method="textrank")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all("word" in r and "tfidf_score" in r for r in result)

    def test_empty_comments(self):
        result = extract_keywords([], top_k=5, method="tfidf")
        assert result == []

    def test_top_k_limit(self):
        comments = [f"关键词{i}" for i in range(50)]
        result = extract_keywords(comments, top_k=3, method="freq")
        assert len(result) <= 3


class TestUrlParser:
    @pytest.mark.asyncio
    async def test_extract_from_long_url(self):
        from core.url_parser import extract_aweme_id

        # 测试长链接格式
        with pytest.raises(ValueError):
            await extract_aweme_id("https://www.douyin.com/invalid")

    @pytest.mark.asyncio
    async def test_extract_from_text(self):
        from core.url_parser import extract_aweme_id

        # 测试无链接文本
        with pytest.raises(ValueError, match="未找到有效链接"):
            await extract_aweme_id("这是一个没有链接的文本")
