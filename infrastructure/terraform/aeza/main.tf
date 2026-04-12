data "aeza_products" "all" {}

resource "aeza_service" "france_exit" {
  name       = var.server_name
  product_id = var.product_id

  auto_prolong = false
}