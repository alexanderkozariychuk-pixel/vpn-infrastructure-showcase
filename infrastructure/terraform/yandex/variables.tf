variable "yandex_token" {
  description = "Yandex Cloud IAM token"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.yandex_token) > 0
    error_message = "Yandex Token must not be empty."
  }
}

variable "yandex_cloud_id" {
  description = "Yandex Cloud ID"
  type        = string

  validation {
    condition     = length(var.yandex_cloud_id) > 0
    error_message = "Yandex Cloud ID must not be empty."
  }
}

variable "yandex_folder_id" {
  description = "Yandex Folder ID"
  type        = string

  validation {
    condition     = length(var.yandex_folder_id) > 0
    error_message = "Yandex Folder ID must not be empty."
  }
}

variable "yandex_zone" {
  description = "Availability zone"
  type        = string
  default     = "ru-central1-a"

  validation {
    condition     = length(var.yandex_zone) > 0
    error_message = "Yandex Zone must not be empty."
  }
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

variable "os_family" {
  description = "Family of the OS image (e.g., ubuntu-2404-lts, ubuntu-2204-lts)"
  type        = string
  default     = "ubuntu-2404-lts"
}

variable "cores" {
  description = "Number of CPU cores for the instance"
  type        = number
  default     = 2
}

variable "memory" {
  description = "Memory in GB for the instance"
  type        = number
  default     = 4
}