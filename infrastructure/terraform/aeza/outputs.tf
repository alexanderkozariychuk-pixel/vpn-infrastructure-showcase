output "exit_servers_ips" {
  description = "Public IPv4 addresses of the exit nodes"
  value = {
    for k, v in aeza_service.exit : k => v.ip
  }
}

output "exit_servers_ids" {
  description = "Aeza Service IDs"
  value = {
    for k, v in aeza_service.exit : k => v.id
  }
}

output "exit_servers_status" {
  description = "Current status of the services"
  value = {
    for k, v in aeza_service.exit : k => v.status
  }
}

output "exit_servers_names" {
  description = "Names of the exit nodes"
  value = {
    for k, v in aeza_service.exit : k => v.name
  }
}