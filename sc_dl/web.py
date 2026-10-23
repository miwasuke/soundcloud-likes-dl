"""ブラウザから一覧取得・ダウンロードするための Web API。

ローカル: `uv run sc-likes-web` で http://localhost:8000 を開く。

SoundCloud のトークンはブラウザ（ブックマークレットで取得し localStorage に保存）から
リクエストごとに X-SC-Token ヘッダーで受け取る。サーバー側には保存しない。
ヘッダーがなければ環境変数 / .env の SC_OAUTH_TOKEN を使う（ローカル用）。
"""

from __future__ import annotations

import os
import tempfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .api import SoundCloud
from .main import load_dotenv, setup_logging
from .service import build_mp3, mp3_filename

STATIC = Path(__file__).parent / "static"
OUT_DIR = Path(os.environ.get("DOWNLOAD_DIR", "downloads")).resolve()
# 指定時は MP3 を S3 に置いて署名付き URL を返す（Lambda 用。レスポンス 6MB 制限を避けるため）
S3_BUCKET = os.environ.get("S3_BUCKET")
PRESIGN_EXPIRES = 3600
# 指定時はこのユーザー ID のトークンだけ受け付ける（カンマ区切り）
ALLOWED_USER_IDS = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}

load_dotenv()
app = FastAPI(title="SoundCloud Likes DL")

_client_id: str | None = os.environ.get("SC_CLIENT_ID") or None
# token -> (SoundCloud, user_id)。トークンが変わっても古いものが溜まらないよう件数を絞る
_sessions: OrderedDict[str, tuple[SoundCloud, int]] = OrderedDict()


def session(token: str | None) -> tuple[SoundCloud, int]:
    global _client_id
    token = token or os.environ.get("SC_OAUTH_TOKEN")
    if not token:
        raise HTTPException(401, "SoundCloud のトークンがありません")
    if token in _sessions:
        _sessions.move_to_end(token)
        return _sessions[token]
    sc = SoundCloud(token, _client_id)
    _client_id = sc.client_id
    user_id = sc.me()["id"]
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        raise HTTPException(403, "このアカウントでは利用できません")
    _sessions[token] = (sc, user_id)
    while len(_sessions) > 5:
        _sessions.popitem(last=False)
    return sc, user_id


@app.exception_handler(httpx.HTTPStatusError)
def soundcloud_error(_: Request, e: httpx.HTTPStatusError) -> JSONResponse:
    # SoundCloud 側の 401/403 はトークン切れとして画面に伝える
    if e.response.status_code in (401, 403):
        return JSONResponse({"detail": "SoundCloud のトークンが無効か期限切れです"}, status_code=401)
    return JSONResponse({"detail": f"SoundCloud API エラー ({e.response.status_code})"}, status_code=502)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/tracks")
def list_tracks(cursor: str | None = None, x_sc_token: str | None = Header(None)) -> dict:
    """Likes を1ページ分返す。画面側は next_cursor が null になるまで続けて呼ぶ。"""
    sc, user_id = session(x_sc_token)
    likes, next_cursor = sc.liked_tracks_page(user_id, cursor)
    return {
        "next_cursor": next_cursor,
        "likes": len(likes),
        "purchase_only": sum(1 for t in likes if not t.can_download and t.purchase_url),
        "tracks": [
            {
                "id": t.id,
                "title": t.title,
                "artist": t.artist,
                "artwork_url": t.artwork_url,
                "permalink_url": t.permalink_url,
            }
            for t in likes
            if t.can_download
        ],
    }


@app.post("/api/tracks/{track_id}/download")
def download(track_id: int, x_sc_token: str | None = Header(None)) -> dict:
    sc, _ = session(x_sc_token)
    track = sc.track(track_id)
    if not track.can_download:
        raise HTTPException(400, "このトラックはダウンロードできません")
    name = mp3_filename(track)
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = build_mp3(sc, track, Path(tmp))
        if S3_BUCKET:
            return {"filename": name, "url": upload_and_presign(mp3, track.id, name)}
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        mp3.replace(OUT_DIR / name)
    return {"filename": name, "url": f"files/{quote(name)}"}


def upload_and_presign(mp3: Path, track_id: int, name: str) -> str:
    import boto3
    from botocore.config import Config

    # リージョンのエンドポイント + SigV4 で署名する（グローバルエンドポイントだと 307 リダイレクトになる）
    region = os.environ.get("AWS_REGION", "ap-northeast-1")
    s3 = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    key = f"tracks/{track_id}.mp3"
    s3.upload_file(str(mp3), S3_BUCKET, key, ExtraArgs={"ContentType": "audio/mpeg"})
    # 別オリジンなので <a download> は効かない。Content-Disposition で保存名を指定する
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f"attachment; filename*=UTF-8''{quote(name)}",
        },
        ExpiresIn=PRESIGN_EXPIRES,
    )


@app.get("/files/{name}")
def files(name: str) -> FileResponse:
    path = (OUT_DIR / name).resolve()
    if path.parent != OUT_DIR or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg", filename=name)


def main() -> None:
    import uvicorn

    setup_logging()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
