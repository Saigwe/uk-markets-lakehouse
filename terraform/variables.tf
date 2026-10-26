variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "uk-markets-lakehouse"
}

variable "region" {
  description = "AWS region (London by default: the data is UK official statistics)."
  type        = string
  default     = "eu-west-2"
}

variable "subnet_ids" {
  description = "Subnets the scheduled Fargate task runs in (needs outbound internet for the ONS and BoE APIs)."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups for the Fargate task (egress only)."
  type        = list(string)
}

variable "schedule" {
  description = "When the pull runs. ONS releases at 07:00 UK time, so 07:30 catches same-day releases."
  type        = string
  default     = "cron(30 7 * * ? *)"
}

variable "image_tag" {
  description = "Pipeline image tag in the ECR repository."
  type        = string
  default     = "latest"
}

variable "alert_email" {
  description = "Where failed runs and audit failures are reported. Empty for no email subscription."
  type        = string
  default     = ""
}

variable "raw_retention_days" {
  description = "Raw downloads move to infrequent access after 30 days and are kept this long in total."
  type        = number
  default     = 1825
}
