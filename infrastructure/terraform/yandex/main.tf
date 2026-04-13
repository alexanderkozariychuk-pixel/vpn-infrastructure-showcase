# Yandex Cloud Russian Bridge VPS

data "yandex_compute_image" "ubuntu" {
  family = var.os_family
}

locals {
  cloud_init_config = <<-EOF
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
    cores  = var.cores
    memory = var.memory
  }

  boot_disk {
    initialize_params {
      image_id = data.yandex_compute_image.ubuntu.id
      size     = 20
      type     = "network-ssd"
    }
  }

  network_interface {
    subnet_id = yandex_vpc_subnet.default.id
    nat       = true
  }

  metadata = {
    user-data = local.cloud_init_config
  }
}