"""CLI と Web で共有する処理（一覧取得・1曲の MP3 生成）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .api import SoundCloud, Track
from .audio import tag_mp3, to_mp3


@dataclass
class LikesSummary:
    total: int
    downloadable: list[Track]
    purchase_only: int

    @property
    def others(self) -> int:
        return self.total - len(self.downloadable) - self.purchase_only


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name[:200] or "untitled"


def mp3_filename(track: Track) -> str:
    return safe_filename(f"{track.artist} - {track.title}") + ".mp3"


def summarize_likes(sc: SoundCloud) -> LikesSummary:
    likes = list(sc.liked_tracks(sc.me()["id"]))
    return LikesSummary(
        total=len(likes),
        downloadable=[t for t in likes if t.can_download],
        purchase_only=sum(1 for t in likes if not t.can_download and t.purchase_url),
    )


def build_mp3(sc: SoundCloud, track: Track, workdir: Path) -> Path:
    """1曲をダウンロードして MP3 に変換・タグ付けし、workdir 内のパスを返す。"""
    raw = workdir / f"{track.id}.src"
    mp3 = workdir / f"{track.id}.mp3"
    sc.download(sc.download_url(track.id), raw)
    to_mp3(raw, mp3)
    tag_mp3(mp3, track.title, track.artist, track.permalink_url, sc.fetch_artwork(track.artwork_url))
    raw.unlink(missing_ok=True)
    return mp3
