terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
}

provider "yandex" {
  token     = var.yandex_token  # never hardcode: see repository history
  cloud_id  = var.cloud_id
  folder_id = var.folder_id
  zone      = "ru-central1-a"
}

resource "yandex_storage_bucket" "tf-state" {
  bucket     = var.state_bucket
  acl        = "private"
  folder_id = var.folder_id
  force_destroy = false

  versioning {
    enabled = true
  }
}

output "bucket_name" {
  value = yandex_storage_bucket.tf-state.bucket
}