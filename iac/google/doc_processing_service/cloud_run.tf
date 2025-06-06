resource "google_cloud_run_v2_service" "doc_processing_service" {
  name     = var.service_name
  location = var.region
  client   = "terraform" # Optional: client version tracking

  template {
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2" # Required for GPU

    containers {
      image = var.image_name
      ports {
        container_port = 8000 # Port the FastAPI app runs on
      }

      resources {
        limits = {
          "cpu"             = "2"       # Example: 2 CPU
          "memory"          = "4Gi"     # Example: 4Gi RAM
          "nvidia.com/gpu"  = "1"       # Request 1 GPU
        }
        startup_cpu_boost = true
      }

      # Optional: Environment variables for the container
      # env {
      #   name  = "TRANSFORMERS_CACHE"
      #   value = "/tmp/transformers_cache" # Example
      # }
      # env {
      #   name = "GEMINI_API_KEY"
      #   value = "<your_gemini_api_key>" # This should be passed via a secret or secure mechanism
      # }
    }

    # Optional: Configure scaling
    scaling {
      min_instance_count = 0 # Can be 1 for faster responses if needed, but incurs cost
      max_instance_count = 2 # Example
    }

    # Optional: Service account for the container
    # service_account = var.service_account_email != "" ? var.service_account_email : null

    # GPU configuration
    # The "nvidia.com/gpu" limit above is the primary way for Gen2.
    # Ensure the region selected in variables.tf supports the type of GPU implicitly requested
    # or configure volume_mounts for specific NVIDIA drivers if needed (usually handled by Cloud Run).
  }

  # Allow unauthenticated invocations for simplicity in this example.
  # For production, restrict this using google_cloud_run_service_iam_member.
  # depends_on = [google_project_service.run_api] # Ensure API is enabled
}

# Optional: IAM policy to allow unauthenticated access (for testing)
# For production, you'd likely want to restrict invokers.
resource "google_cloud_run_v2_service_iam_member" "allow_public_doc_service" {
  project  = google_cloud_run_v2_service.doc_processing_service.project
  location = google_cloud_run_v2_service.doc_processing_service.location
  name     = google_cloud_run_v2_service.doc_processing_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
  # Condition for this binding to avoid errors if the service is not yet created.
  # This might not be strictly necessary with implicit dependencies, but good for clarity.
  # depends_on = [google_cloud_run_v2_service.doc_processing_service]
}

# It's good practice to enable the Run API if not already enabled.
# resource "google_project_service" "run_api" {
#   project = var.project_id
#   service = "run.googleapis.com"
#   disable_on_destroy = false # Set to true if you want the API disabled when infrastructure is destroyed
# }

# Similarly, for Artifact Registry API
# resource "google_project_service" "artifact_registry_api" {
#   project = var.project_id
#   service = "artifactregistry.googleapis.com"
#   disable_on_destroy = false
# }
