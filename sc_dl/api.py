"""SoundCloud api-v2 の薄いラッパー。"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import parse_qsl, urlsplit

import httpx

log = logging.getLogger(__name__)

API = "https://api-v2.soundcloud.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


@dataclass
class Track:
    id: int
    title: str
    artist: str
    permalink_url: str
    artwork_url: str | None
    downloadable: bool
    has_downloads_left: bool
    purchase_url: str | None

    @property
    def can_download(self) -> bool:
        return self.downloadable and self.has_downloads_left

    @classmethod
    def from_json(cls, t: dict) -> "Track":
        user = t.get("user") or {}
        return cls(
            id=t["id"],
            title=t.get("title") or str(t["id"]),
            artist=user.get("username") or "",
            permalink_url=t.get("permalink_url") or "",
            # トラック画像がなければアカウントのアバターで代用
            artwork_url=t.get("artwork_url") or user.get("avatar_url"),
            downloadable=bool(t.get("downloadable")),
            has_downloads_left=bool(t.get("has_downloads_left")),
            purchase_url=t.get("purchase_url"),
        )


def fetch_client_id(client: httpx.Client) -> str:
    """soundcloud.com の JS バンドルから client_id を取得する。"""
    html = client.get("https://soundcloud.com/").text
    scripts = re.findall(r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html)
    # client_id は後ろの方のバンドルに入っていることが多い
    for src in reversed(scripts):
        m = re.search(r'client_id\s*[:=]\s*"([a-zA-Z0-9]{32})"', client.get(src).text)
        if m:
            return m.group(1)
    raise RuntimeError("client_id を取得できませんでした")


def artwork_original(url: str | None) -> list[str]:
    """高解像度順に試すアートワーク URL の候補。"""
    if not url:
        return []
    return [url.replace("-large.", s) for s in ("-original.", "-t500x500.")] + [url]


class SoundCloud:
    def __init__(self, oauth_token: str, client_id: str | None = None):
        self.http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, read=120.0),
            follow_redirects=True,
        )
        self.client_id = client_id or fetch_client_id(self.http)
        self.auth = {"Authorization": f"OAuth {oauth_token}"}

    def _get(self, url: str, params: dict | None = None) -> dict:
        params = {"client_id": self.client_id, **(params or {})}
        for attempt in range(5):
            r = self.http.get(url, params=params, headers=self.auth)
            if r.status_code == 429 or r.status_code >= 500:
                wait = 2**attempt * 5
                log.warning("HTTP %s: %s 秒待って再試行します", r.status_code, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return r.json()

    def me(self) -> dict:
        return self._get(f"{API}/me")

    def liked_tracks(self, user_id: int) -> Iterator[Track]:
        cursor: str | None = None
        while True:
            tracks, next_cursor = self.liked_tracks_page(user_id, cursor)
            yield from tracks
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def liked_tracks_page(self, user_id: int, cursor: str | None = None,
                          limit: int = 200) -> tuple[list[Track], str | None]:
        """Likes を1ページ取得し、(トラック, 次ページの cursor) を返す。"""
        params: dict = {"limit": limit, "linked_partitioning": 1}
        if cursor:
            params["offset"] = cursor
        data = self._get(f"{API}/users/{user_id}/track_likes", params)
        collection = data.get("collection", [])
        tracks = [Track.from_json(item["track"]) for item in collection if item.get("track")]
        # httpx は params を渡すと URL 側のクエリを置き換えるので、next_href からは offset だけ取り出して使う
        next_href = data.get("next_href")
        next_cursor = dict(parse_qsl(urlsplit(next_href).query)).get("offset") if next_href and collection else None
        return tracks, next_cursor

    def track(self, track_id: int) -> Track:
        return Track.from_json(self._get(f"{API}/tracks/{track_id}"))

    def download_url(self, track_id: int) -> str:
        return self._get(f"{API}/tracks/{track_id}/download")["redirectUri"]

    def download(self, url: str, dest) -> str:
        """URL をファイルに保存し、Content-Type を返す。"""
        with self.http.stream("GET", url) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
            return r.headers.get("content-type", "")

    def fetch_artwork(self, url: str | None) -> tuple[bytes, str] | None:
        for candidate in artwork_original(url):
            r = self.http.get(candidate)
            if r.status_code == 200:
                return r.content, r.headers.get("content-type", "image/jpeg")
        return None
