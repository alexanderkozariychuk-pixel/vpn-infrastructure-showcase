# Output data from the Aeza module
output "aeza_exit_ip" {
  description = "Public IP of France exit node"
  value       = module.aeza_exit.exit_server_ip   # Let's assume that the module returns such output
}

output "aeza_exit_id" {
  description = "Aeza service ID"
  value       = module.aeza_exit.exit_server_id
}

# Output data from the Yandex module
output "yandex_bridge_ip" {
  description = "Public IP of Russian bridge node"
  value       = module.yandex_bridge.russian_bridge_ip
}

output "yandex_bridge_ssh_command" {
  description = "SSH command to connect to Russian bridge"
  value       = module.yandex_bridge.ssh_command
}