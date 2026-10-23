"""MP3 変換と ID3 タグ付け。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from mutagen.id3 import APIC, ID3, TIT2, TPE1, WXXX
from mutagen.mp3 import MP3


def is_mp3(path: Path) -> bool:
    try:
        return MP3(path).info is not None
    except Exception:
        return False


def to_mp3(src: Path, dest: Path, bitrate: str = "320k") -> None:
    """元ファイルが MP3 ならコピー、それ以外は ffmpeg で MP3 に変換する。"""
    if is_mp3(src):
        shutil.copyfile(src, dest)
        return
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-map", "0:a:0", "-map_metadata", "-1",
            "-codec:a", "libmp3lame", "-b:a", bitrate,
            str(dest),
        ],
        check=True,
    )


def tag_mp3(path: Path, title: str, artist: str, url: str,
            cover: tuple[bytes, str] | None) -> None:
    # 元ファイル由来のタグは消して付け直す
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(WXXX(encoding=3, desc="SoundCloud", url=url))
    if cover:
        data, mime = cover
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    tags.save(path, v2_version=3)
