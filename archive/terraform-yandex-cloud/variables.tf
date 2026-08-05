# Variables for Aeza
variable "aeza_api_key" {
  description = "API key for Aeza"
  type        = string
  sensitive   = true
}

# Переменные для Yandex Cloud
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
  description = "Yandex Cloud availability zone"
  type        = string
  default     = "ru-central1-a"
}

variable "yandex_server_name" {
  description = "Name for the Yandex VM"
  type        = string
  default     = "ru-bridge-01"
}

variable "yandex_cores" {
  description = "Number of CPU cores for Yandex VM"
  type        = number
  default     = 2
}

variable "yandex_memory" {
  description = "Memory in GB for Yandex VM"
  type        = number
  default     = 4
}

# Common variables
variable "ssh_public_key" {
  description = "Public SSH key for VMs"
  type        = string
}