terraform {
  required_version = ">= 1.5"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.31"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # NOTE: intentionally still local state, not an S3 backend.
  # An S3 (+ DynamoDB lock table) backend needs those resources to already
  # exist before `terraform init` can even run - we don't have real AWS
  # infrastructure yet, so switching this on would break CI rather than
  # help it. Once a real bucket/table exists, uncomment and fill in:
  #
  # backend "s3" {
  #   bucket         = "<your-tfstate-bucket>"
  #   key            = "myapp/terraform.tfstate"
  #   region         = "<your-region>"
  #   dynamodb_table = "<your-lock-table>"
  #   encrypt        = true
  # }
}

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}

provider "helm" {
  kubernetes {
    config_path    = var.kubeconfig_path
    config_context = var.kube_context
  }
}

# Not referenced by any resource yet - this is here so credentials are
# already flowing end-to-end from GitHub Secrets through CI into Terraform
# (see .github/workflows/ci.yml). Credentials are read from the standard
# AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY environment variables - never
# hardcode them here. Once real AWS resources are introduced (S3 state
# backend, ECR, EKS), they slot in as `resource "aws_..."` blocks below,
# reusing this provider without touching the credential plumbing again.
provider "aws" {
  region = var.aws_region
}
