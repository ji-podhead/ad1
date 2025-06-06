variable "project_id" {
  description = "The Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "The Google Cloud region for deployment."
  type        = string
  default     = "europe-west1" # Example region, choose one with GPU support
}

variable "service_name" {
  description = "Name for the Cloud Run service."
  type        = string
  default     = "doc-processing-service"
}

variable "image_name" {
  description = "Full path to the Docker image in Artifact Registry (e.g., REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME:TAG)."
  type        = string
  # Example: "europe-west1-docker.pkg.dev/my-project/my-repo/doc-processing-service:latest"
  # This will need to be set when applying, after the image is pushed.
}

variable "service_account_email" {
  description = "The email of the service account for the Cloud Run service."
  type        = string
  default     = "" # Optional: If a specific SA is used. Otherwise, uses default compute SA.
}
