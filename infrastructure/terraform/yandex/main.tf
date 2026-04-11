# Yandex Cloud Russian Bridge VPS

resource "yandex_vpc_network" "default" {
  name = "ru-bridge-network"
}

resource "yandex_vpc_subnet" "default" {
  name           = "ru-bridge-subnet"
  zone           = var.yandex_zone
  network_id     = yandex_vpc_network.default.id
  v4_cidr_blocks = ["10.1.0.0/16"]
}

resource "yandex_compute_instance" "russian_bridge" {
  name        = var.server_name
  zone        = var.yandex_zone
  platform_id = "standard-v3"

  resources {
    cores  = 2
    memory = 4
  }

  boot_disk {
    initialize_params {
      image_id = "fd8vmcue7aaj4p5e9v8t"  # Ubuntu 24.04 LTS
      size     = 20
      type     = "network-ssd"
    }
  }

  network_interface {
    subnet_id = yandex_vpc_subnet.default.id
    nat       = true
  }

  metadata = {
    user-data = <<-EOF
      #cloud-config
      users:
        - name: ubuntu
          ssh-authorized-keys:
            - ${var.ssh_public_key}
          sudo: ['ALL=(ALL) NOPASSWD:ALL']
          groups: sudo
      packages:
        - curl
        - git
        - ufw
      runcmd:
        - ufw allow 22/tcp
        - ufw --force enable
        - apt update && apt upgrade -y
      EOF
  }
}

output "russian_bridge_ip" {
  description = "Public IP of Russian Bridge"
  value       = yandex_compute_instance.russian_bridge.network_interface[0].nat_ip_address
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh ubuntu@${yandex_compute_instance.russian_bridge.network_interface[0].nat_ip_address}"
}