# Example usage for gmailApi Terraform module

module "gmail_api" {
  source       = "./iac/google/gmailApi"
  project_id   = "your-gcp-project-id"
  region       = "europe-west6"
  support_email = "admin@yourdomain.com"
}
