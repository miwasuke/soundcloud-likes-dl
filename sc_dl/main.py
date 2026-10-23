"""SoundCloud の Likes からダウンロード可能なトラックを MP3 で保存する CLI。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

from .api import SoundCloud
from .service import build_mp3, mp3_filename, summarize_likes

log = logging.getLogger("sc_dl")


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def resolve_token() -> str:
    if token := os.environ.get("SC_OAUTH_TOKEN"):
        return token
    if param := os.environ.get("SC_OAUTH_TOKEN_SSM_PARAM"):
        import boto3

        return boto3.client("ssm").get_parameter(Name=param, WithDecryption=True)["Parameter"]["Value"]
    sys.exit("SC_OAUTH_TOKEN または SC_OAUTH_TOKEN_SSM_PARAM を設定してください")


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # 署名付き URL や client_id がログに出ないようにする
    logging.getLogger("httpx").setLevel(logging.WARNING)


def new_client() -> SoundCloud:
    load_dotenv()
    return SoundCloud(resolve_token(), os.environ.get("SC_CLIENT_ID") or None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("downloads"), help="保存先ディレクトリ")
    p.add_argument("--limit", type=int, help="ダウンロードする最大件数（検証用）")
    p.add_argument("--dry-run", action="store_true", help="一覧を表示するだけでダウンロードしない")
    args = p.parse_args(argv)

    setup_logging()
    sc = new_client()
    summary = summarize_likes(sc)
    log.info("Likes %d 件 / DL可能 %d 件 / purchase のみ %d 件 / その他 %d 件",
             summary.total, len(summary.downloadable), summary.purchase_only, summary.others)

    targets = summary.downloadable[: args.limit] if args.limit is not None else summary.downloadable
    if args.dry_run:
        for t in targets:
            print(f"[DL] {t.artist} - {t.title}  ({t.permalink_url})")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(targets, 1):
            try:
                dest = args.out / mp3_filename(t)
                build_mp3(sc, t, Path(tmp)).replace(dest)
                log.info("[%d/%d] 保存: %s", i, len(targets), dest)
            except Exception as e:  # 1曲の失敗で全体を止めない
                failed += 1
                log.error("[%d/%d] 失敗: %s - %s (%s)", i, len(targets), t.artist, t.title, e)

    log.info("完了: 成功 %d 件 / 失敗 %d 件", len(targets) - failed, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
