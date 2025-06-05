# Terraform for GCP Cloud Run & GKE Deployment of ad1 App

variable "project_id" {}
variable "region" { default = "europe-west6" }
variable "frontend_image" { default = "gcr.io/YOUR_PROJECT/ad1-frontend:latest" }
variable "backend_image" { default = "gcr.io/YOUR_PROJECT/ad1-backend:latest" }
variable "db_image" { default = "postgres:15" }

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud Run for Frontend (public)
resource "google_cloud_run_service" "frontend" {
  name     = "ad1-frontend"
  location = var.region
  template {
    spec {
      containers {
        image = var.frontend_image
        ports { container_port = 3000 }
      }
    }
  }
  traffics { percent = 100, latest_revision = true }
  autogenerate_revision_name = true
}

resource "google_cloud_run_service_iam_member" "frontend_public" {
  service = google_cloud_run_service.frontend.name
  location = google_cloud_run_service.frontend.location
  role = "roles/run.invoker"
  member = "allUsers"
}

# Cloud Run for Backend (private)
resource "google_cloud_run_service" "backend" {
  name     = "ad1-backend"
  location = var.region
  template {
    spec {
      containers {
        image = var.backend_image
        ports { container_port = 8001 }
      }
    }
  }
  traffics { percent = 100, latest_revision = true }
  autogenerate_revision_name = true
}

# Example for GKE (Kubernetes) deployment (optional, not full manifest)
# module "gke" {
#   source  = "terraform-google-modules/kubernetes-engine/google//modules/private-cluster"
#   project_id = var.project_id
#   name   = "ad1-gke"
#   region = var.region
#   ...
# }
#
# resource "kubernetes_deployment" "frontend" { ... }
# resource "kubernetes_service" "frontend" { ... }

output "frontend_url" {
  value = google_cloud_run_service.frontend.status[0].url
}
