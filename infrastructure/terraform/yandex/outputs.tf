output "russian_bridge_ip" {
  description = "Public IP address of the Russian Bridge"
  value       = yandex_compute_instance.russian_bridge.network_interface[0].nat_ip_address
}

output "russian_bridge_id" {
  description = "Instance ID"
  value       = yandex_compute_instance.russian_bridge.id
}

output "ssh_command" {
  description = "Command to connect to the server"
  value       = "ssh ubuntu@${yandex_compute_instance.russian_bridge.network_interface[0].nat_ip_address}"
}

output "internal_ip" {
  description = "Internal IP address of the instance"
  value       = yandex_compute_instance.russian_bridge.network_interface[0].ip_address
}