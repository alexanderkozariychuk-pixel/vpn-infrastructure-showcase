terraform {
  required_providers {
    aeza = {
      source  = "scinfra-pro/aeza"
      version = "~> 0.3"
    }
  }
}

provider "aeza" {
  api_key = var.aeza_api_key 
}