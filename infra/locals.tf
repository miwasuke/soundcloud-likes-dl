locals {
  environment   = "dev"
  resource_name = "soundcloud-likes-dl"
  name          = "${var.name_prefix}-${local.resource_name}"

  tags = {
    terraform   = true
    environment = local.environment
    service     = local.resource_name
  }
}
