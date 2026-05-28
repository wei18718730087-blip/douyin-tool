from typing import Optional

from pydantic import BaseModel, Field


class VideoInfo(BaseModel):
    aweme_id: str
    title: str
    author: str = ""
    duration: Optional[int] = None
    video_url: Optional[str] = None
    file_path: Optional[str] = None
    thumbnail: Optional[str] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None


class Comment(BaseModel):
    cid: str
    text: str
    author: str = ""
    author_uid: str = ""
    create_time: int = 0
    digg_count: int = 0
    reply_count: int = 0


class Keyword(BaseModel):
    word: str
    tfidf_score: Optional[float] = None
    count: Optional[int] = None
