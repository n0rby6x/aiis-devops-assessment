resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace
  }
}

resource "helm_release" "app" {
  name      = var.release_name
  chart     = "${path.module}/../helm"
  namespace = kubernetes_namespace.app.metadata[0].name

  # Wait for the deployment to become ready before Terraform reports success.
  wait    = true
  timeout = 300

  set {
    name  = "image.repository"
    value = var.image_repository
  }

  set {
    name  = "image.tag"
    value = var.image_tag
  }

  set {
    name  = "environment"
    value = var.environment
  }
}
