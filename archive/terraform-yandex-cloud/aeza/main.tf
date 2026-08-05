data "aeza_products" "all" {}

locals {
  selected_products = {
    for name, product_name in var.exit_nodes :
    name => [for p in data.aeza_products.all.products : p.id if p.name == product_name][0]
  }
}

resource "aeza_service" "exit" {
  for_each = local.selected_products

  name         = "${each.key}-exit"
  product_id   = each.value
  auto_prolong = false
}

# Resource for managing SSH keys via API
resource "null_resource" "add_ssh_key" {
  # For each server created, its own null_resource instance is created.
  for_each = aeza_service.exit

  # The script will be executed ONLY after the server (aeza_service) is created
  depends_on = [aeza_service.exit]

  provisioner "local-exec" {
    command = <<-EOT
      echo "Adding an SSH key to the server: ${each.value.name} (ID: ${each.value.id})"
      curl -X POST https://my.aeza.net/api/sshkeys \
        -H "X-API-Key: ${var.aeza_api_key}" \
        -H "Content-Type: application/json" \
        -d '{
          "name": "tf-${each.value.name}",
          "pubKey": "${chomp(file(var.ssh_public_key_path))}"
        }'
      echo -e "\nSSH-key added."
    EOT
  }
}