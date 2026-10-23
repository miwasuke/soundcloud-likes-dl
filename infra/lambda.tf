resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "app" {
  function_name = local.name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}@${data.aws_ecr_image.app.image_digest}"
  architectures = ["arm64"]

  # WAV からの変換を考慮して余裕を持たせる
  memory_size = 2048
  timeout     = 300
  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      S3_BUCKET        = aws_s3_bucket.files.id
      ALLOWED_USER_IDS = join(",", var.allowed_user_ids)
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy_attachment.lambda_logs]
}

# 認証は SoundCloud トークン + ALLOWED_USER_IDS で行うので URL 自体は公開
resource "aws_lambda_function_url" "app" {
  function_name      = aws_lambda_function.app.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.app.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# 公開 Function URL には InvokeFunction 権限（Function URL 経由に限定）も必要
resource "aws_lambda_permission" "url_invoke" {
  statement_id             = "FunctionURLInvokeAllowPublicAccess"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.app.function_name
  principal                = "*"
  invoked_via_function_url = true
}
