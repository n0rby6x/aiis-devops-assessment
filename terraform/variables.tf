variable "namespace" {
  type        = string
  description = "Kubernetes namespace the application is deployed into."
  default     = "myapp"
}

variable "environment" {
  type        = string
  description = "Application environment injected into the app (ENVIRONMENT env var / GET /env). Maps 1:1 from the git branch: dev->dev, uat->uat, main->prod."
  default     = "dev"

  validation {
    condition     = contains(["dev", "uat", "prod"], var.environment)
    error_message = "environment must be one of: dev, uat, prod."
  }
}

variable "image_tag" {
  type        = string
  description = "Container image tag to deploy (e.g. the CI pipeline's CI_COMMIT_SHORT_SHA)."
}

variable "image_repository" {
  type        = string
  description = "Container image repository, e.g. ghcr.io/<org>/<repo>/myapp."
  default     = "myapp"
}

variable "release_name" {
  type        = string
  description = "Helm release name."
  default     = "myapp"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to the kubeconfig file used by the kubernetes/helm providers."
  default     = "~/.kube/config"
}

variable "kube_context" {
  type        = string
  description = "kubeconfig context to use (null = current-context)."
  default     = null
}

variable "aws_region" {
  type        = string
  description = "AWS region for the (currently unused) aws provider - reserved for a future S3 state backend / ECR / EKS integration."
  default     = "eu-central-1"
}
