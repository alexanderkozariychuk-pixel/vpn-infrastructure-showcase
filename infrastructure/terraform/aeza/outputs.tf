output "exit_server_ip" {
  description = "Public IPv4 address of the France Exit Node"
  value       = aeza_service.france_exit.ip
}

output "exit_server_id" {
  description = "Aeza Service ID"
  value       = aeza_service.france_exit.id
}

output "exit_server_status" {
  description = "Current status of the service"
  value       = aeza_service.france_exit.status
}

output "exit_server_name" {
  description = "Name of the Exit Node"
  value       = aeza_service.france_exit.name
}

output "available_products" {
  description = "List of all available Aeza products (for reference)"
  value       = data.aeza_products.all.products
}