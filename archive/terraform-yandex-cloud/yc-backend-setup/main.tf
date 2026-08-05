terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
}

provider "yandex" {
  token     = "y0__xC5063lCBjB3RMgjqT6hhcyP4miCsfODqQFIAP05aHjxllKWA"
  cloud_id  = "b1ghuve6menqskf2ha6r"
  folder_id = "b1gjqm14p47edvaj74tk"
  zone      = "ru-central1-a"
}

resource "yandex_storage_bucket" "tf-state" {
  bucket     = "tf-state-13880990akoz"
  acl        = "private"
  folder_id  = "b1gjqm14p47edvaj74tk"
  force_destroy = false

  versioning {
    enabled = true
  }
}

output "bucket_name" {
  value = yandex_storage_bucket.tf-state.bucket
}