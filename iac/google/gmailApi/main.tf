# Terraform for Gmail API and OAuth Client

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "gmail" {
  project = var.project_id
  service = "gmail.googleapis.com"
}

resource "google_project_service" "iam" {
  project = var.project_id
  service = "iam.googleapis.com"
}

resource "google_iap_client" "frontend" {
  display_name = "ad1-frontend"
  brand        = google_iap_brand.default.name
  redirect_uris = [
    "http://localhost:3000/oauth2callback"
    # Add your production URI here
  ]
}

resource "google_iap_brand" "default" {
  support_email     = var.support_email
  application_title = "ad1 Gmail App"
}

output "client_id" {
  value = google_iap_client.frontend.client_id
}

output "client_secret" {
  value = google_iap_client.frontend.secret
}

variable "project_id" {}
variable "region" { default = "europe-west6" }
variable "support_email" {}
