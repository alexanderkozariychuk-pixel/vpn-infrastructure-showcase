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
  default     = "fr" # France (Paris)
}

variable "product_id" {
  description = "Aeza product ID (tariff ID)"
  type        = number
}

variable "exit_nodes" {
  description = "Map of exit nodes to create. Key is a unique identifier, value is the product name."
  type        = map(string)
  default = {
    france = "PARs-1"
    # netherlands = "NLs-1"
  }
}

variable "ssh_public_key_path" {
  description = "Path to the public SSH key file"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}
