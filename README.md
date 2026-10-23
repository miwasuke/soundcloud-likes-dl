# soundcloud-likes-dl

SoundCloud の Likes から、アーティストがダウンロードを許可しているトラックだけを MP3 で保存する Web アプリです。

- 外部サイトへの購入・Free Download リンク（purchase）だけのトラックは対象外です
- WAV などの元ファイルは 320kbps の MP3 に変換します
- タイトル・作者（アカウント名）・カバー画像（トラックのサムネイル）を ID3 タグとして埋め込みます

> アーティストが許可したダウンロードのみを対象にしています。私的利用の範囲で使ってください。

## 構成

```
ブラウザ ──(X-SC-Token ヘッダー)──> Lambda Function URL ──> SoundCloud api-v2
   │                                   │  ダウンロード → ffmpeg で MP3 化 → タグ付け
   │                                   └─> S3（tracks/ は1日で自動削除）
   └──(署名付き URL)──────────────────────> S3 から MP3 をダウンロード
```

| リソース | 内容 |
|---|---|
| Lambda | ffmpeg 入りコンテナ（arm64 / 2GB / 5分）。Lambda Web Adapter で FastAPI を実行 |
| Function URL | 認証なしで公開。API は `allowed_user_ids` のトークンでしか使えない |
| S3 | 変換した MP3 の受け渡し用。署名付き URL は1時間有効 |
| ECR | コンテナイメージ。直近5イメージだけ残す |

SoundCloud のトークンはブラウザの localStorage にだけ保存し、リクエストごとにヘッダーで送ります。サーバー側には保存しないため、Secrets Manager などは使いません。

## 必要なもの

- AWS CLI（デプロイ先アカウントにログイン済み）
- Docker
- Terraform 1.14 系（`tfenv` を使う場合は `infra/.terraform-version` を参照）
- tfstate を置く S3 バケット（既存のもの）
- ローカルで動かす場合: [uv](https://docs.astral.sh/uv/)、ffmpeg

## 設定する変数

`infra/` に次の2ファイルを作ります。どちらも `.gitignore` 済みなのでコミットされません。

```bash
cp infra/backend.hcl.example infra/backend.hcl
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

### infra/backend.hcl（tfstate の保存先）

| 項目 | 説明 |
|---|---|
| `bucket` | tfstate を置く既存の S3 バケット |
| `key` | tfstate のパス |
| `region` | バケットのリージョン |

### infra/terraform.tfvars（リソースの設定）

| 変数 | 必須 | 説明 |
|---|---|---|
| `name_prefix` | ○ | リソース名の接頭辞。`<name_prefix>-soundcloud-likes-dl` が Lambda・ECR・S3 バケットの名前になる。S3 バケット名は世界で一意なので、他人と被らない値にする |
| `allowed_user_ids` | ○ | 利用を許可する SoundCloud のユーザー ID のリスト |
| `region` | | デプロイ先のリージョン（既定: `ap-northeast-1`） |

### 変数を変更するとき

- `allowed_user_ids` を変更する場合は、`terraform.tfvars` を書き換えて `./deploy.sh` を実行すると Lambda の環境変数が更新されます。
- `name_prefix` や `region` を変更する場合は、リソースが作り直しになり、URL も変わります。古いリソースを `terraform destroy` で消してから変更するのが安全です。
- `backend.hcl` を変更した場合は、`terraform -chdir=infra init -backend-config=backend.hcl -reconfigure` を実行します（state を移すときは `-migrate-state`）。

## SoundCloud のユーザー ID を調べる

1. ログイン済みの soundcloud.com で DevTools → Application → Cookies を開き、`oauth_token` の値を確認する
2. `.env` を作って値を設定する

   ```bash
   cp .env.example .env   # SC_OAUTH_TOKEN= に値を貼る
   ```

3. 次のコマンドを実行する。ログに `ユーザー: <名前> (id=<ユーザー ID>)` と表示される

   ```bash
   uv run sc-likes-dl --dry-run --limit 0
   ```

## デプロイ

```bash
./deploy.sh
```

`deploy.sh` は次の順で処理します。

1. `terraform init`（`backend.hcl` を使用）
2. 初回だけ ECR リポジトリを作成する（plan が表示されるので `yes` を入力）
3. コンテナイメージをビルドして ECR に push する（タグは日時）
4. 全体の plan を表示し、`yes` を入力すると反映する
5. 最後にアプリの URL を表示する

コードを変更したときも、同じく `./deploy.sh` を実行します。

## 使い方

1. デプロイ後に表示された URL をブラウザで開く
2. 「トークン設定」にある **SC トークン取得** をブックマークバーへドラッグする
3. ログイン済みの soundcloud.com を開き、そのブックマークをクリックする
4. アプリがトークン付きで開き、Likes の一覧が自動で表示される
5. 各曲の **DL**、または **表示中をすべてDL** でダウンロードする

- ブックマークレットは、ドラッグしたページの URL を開くように作られます。URL が変わったら（ローカルとデプロイ先など）、そのページから登録し直してください
- トークンの期限が切れると設定パネルが表示されます。同じブックマークをもう一度クリックすれば更新できます
- ブックマークレットで取れない場合は、`oauth_token` を設定パネルに貼り付けても使えます

## ローカルで動かす

```bash
brew install ffmpeg
uv sync
cp .env.example .env   # SC_OAUTH_TOKEN を設定
```

| コマンド | 内容 |
|---|---|
| `uv run sc-likes-web` | http://localhost:8000 で Web 画面を起動する（MP3 は `downloads/` にも保存） |
| `uv run sc-likes-dl --dry-run` | DL 可能なトラックを一覧表示する |
| `uv run sc-likes-dl --limit 3` | 先頭3曲を `downloads/` に保存する |
| `uv run sc-likes-dl` | DL 可能な全曲を `downloads/` に保存する |

## 削除

```bash
terraform -chdir=infra destroy
```

S3 バケットと ECR リポジトリは中身ごと削除されます。

## 費用の目安

月100曲程度なら、Lambda・S3・データ転送は無料枠に収まります。主な費用は ECR のイメージ保存（1イメージ約250MB）で、月 $0.05〜0.15 程度です。
