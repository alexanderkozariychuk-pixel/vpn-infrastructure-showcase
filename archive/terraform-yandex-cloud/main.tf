# Terraform root configuration for managing all infrastructure

terraform {
  required_version = ">= 1.5"
  required_providers {
    # Providers are declared in modules, they are not needed here unless we use them directly
  }
}

# Module for the exit node in France (Aeza)
module "aeza_exit" {
  source = "./aeza"

  aeza_api_key = var.aeza_api_key
  # If there are other variables in the module, please specify them
  # For example:
  # product_id   = var.aeza_product_id
  # server_name  = var.aeza_server_name
  # ssh_public_key_path = var.ssh_public_key_path
}

# Module for the Russian bridge node (Yandex Cloud)
module "yandex_bridge" {
  source = "./yandex"

  yandex_token     = var.yandex_token
  yandex_cloud_id  = var.yandex_cloud_id
  yandex_folder_id = var.yandex_folder_id
  yandex_zone      = var.yandex_zone
  server_name      = var.yandex_server_name
  ssh_public_key   = var.ssh_public_key
  cores            = var.yandex_cores
  memory           = var.yandex_memory
}