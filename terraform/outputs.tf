output "namespace" {
  description = "Namespace the application was deployed into."
  value       = kubernetes_namespace.app.metadata[0].name
}

output "release_name" {
  description = "Name of the deployed Helm release."
  value       = helm_release.app.name
}

output "release_status" {
  description = "Status of the Helm release as reported by Terraform."
  value       = helm_release.app.status
}

output "app_version" {
  description = "Chart appVersion that was deployed."
  value       = helm_release.app.metadata[0].app_version
}
