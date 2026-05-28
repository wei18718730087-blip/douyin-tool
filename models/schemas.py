from pydantic import BaseModel


class VideoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    output_dir: str = "./downloads"


class KeywordsRequest(BaseModel):
    texts: list[str]
    count: int = 20
    method: str = "mixed"


class CommentsRequest(BaseModel):
    url: str
    max_comments: int = 50
