# 値は terraform.tfvars で指定する（terraform.tfvars.example を参照）

variable "region" {
  description = "デプロイ先のリージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "name_prefix" {
  description = "リソース名の接頭辞。S3 バケット名にも使うので、世界で一意になる値にする"
  type        = string
}

variable "allowed_user_ids" {
  description = "利用を許可する SoundCloud のユーザー ID"
  type        = list(number)
}

variable "image_tag" {
  description = "デプロイするコンテナイメージのタグ（deploy.sh が指定する）。省略時は ECR の最新イメージ"
  type        = string
  default     = null
}
