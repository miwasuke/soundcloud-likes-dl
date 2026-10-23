terraform {
  required_version = "~> 1.14.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # bucket / key / region は backend.hcl で指定する（backend.hcl.example を参照）
  backend "s3" {
    encrypt = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}
