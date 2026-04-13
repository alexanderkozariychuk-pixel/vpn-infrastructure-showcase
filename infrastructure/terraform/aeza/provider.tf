terraform {
  required_providers {
    aeza = {
      source  = "scinfra-pro/aeza"
      version = "~> 0.3"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "aeza" {
  api_key = var.aeza_api_key
}
