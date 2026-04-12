variable "aeza_api_key" {
  description = "Aeza API Key"
  type        = string
  sensitive   = true
}

variable "server_name" {
  description = "Name of the Exit Node"
  type        = string
  default     = "fr-exit-01"
}

variable "location" {
  description = "Location code for France"
  type        = string
  default     = "fr"   # France (Paris)
}

variable "ssh_public_key" {
  description = "Your SSH public key"
  type        = string
}

variable "product_id" {
  description = "Aeza product ID (tariff ID)"
  type        = number
}