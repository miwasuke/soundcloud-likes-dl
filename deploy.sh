#!/usr/bin/env bash
# コンテナイメージをビルドして ECR に push し、Terraform で Lambda を更新する
# 事前に infra/backend.hcl と infra/terraform.tfvars を用意しておく（README 参照）
set -euo pipefail

cd "$(dirname "$0")"
TAG=$(date +%Y%m%d%H%M%S)

for f in infra/backend.hcl infra/terraform.tfvars; do
  [[ -f $f ]] || { echo "$f がありません。${f}.example をコピーして値を設定してください" >&2; exit 1; }
done
aws sts get-caller-identity >/dev/null

terraform -chdir=infra init -input=false -backend-config=backend.hcl >/dev/null
# 初回だけ ECR リポジトリを先に作る（イメージがないと Lambda の plan ができないため）
if ! terraform -chdir=infra state list 2>/dev/null | grep -qx 'aws_ecr_repository.app'; then
  terraform -chdir=infra apply -target=aws_ecr_repository.app -var image_tag="$TAG"
fi
REPO=$(terraform -chdir=infra output -raw ecr_repository_url)
REGISTRY=${REPO%%/*}                       # <account>.dkr.ecr.<region>.amazonaws.com
REGION=$(cut -d. -f4 <<<"$REGISTRY")

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/arm64 --provenance=false -t "$REPO:$TAG" .
docker push "$REPO:$TAG"

# plan を表示し、yes と入力したときだけ反映する
terraform -chdir=infra apply -var image_tag="$TAG" "$@"
echo "URL: $(terraform -chdir=infra output -raw url)"
