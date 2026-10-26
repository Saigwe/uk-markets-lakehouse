terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
  # Remote state in production, e.g.:
  # backend "s3" { bucket = "<state-bucket>" key = "uk-markets-lakehouse/terraform.tfstate" region = "eu-west-2" }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      project    = var.project
      managed_by = "terraform"
    }
  }
}
