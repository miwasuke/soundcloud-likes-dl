# 変換した MP3 の受け渡し用。ブラウザが署名付き URL で取得したら不要なので1日で消す
resource "aws_s3_bucket" "files" {
  bucket        = local.name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    id     = "expire-tracks"
    status = "Enabled"
    filter {
      prefix = "tracks/"
    }
    expiration {
      days = 1
    }
  }
}
