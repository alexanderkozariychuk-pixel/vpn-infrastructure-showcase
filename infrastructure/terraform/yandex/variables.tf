variable "yandex_token" {
  description = "Yandex Cloud IAM token"
  type        = string
  sensitive   = true
}

variable "yandex_cloud_id" {
  description = "Yandex Cloud ID"
  type        = string
}

variable "yandex_folder_id" {
  description = "Yandex Folder ID"
  type        = string
}

variable "yandex_zone" {
  description = "Availability zone"
  type        = string
  default     = "ru-central1-a"
}

variable "server_name" {
  description = "Name of the Russian Bridge VPS"
  type        = string
  default     = "ru-bridge-01"
}

variable "ssh_public_key" {
  description = "Your SSH public key"
  type        = string
}