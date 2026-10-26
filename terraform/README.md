# Terraform: the lakehouse on AWS

| File | Resources |
|---|---|
| `storage.tf` | One S3 bucket: `raw/` (every downloaded release, immutable), `warehouse/` (Iceberg), `athena/` (results). Versioned, KMS-encrypted, public access blocked, lifecycle rules. |
| `catalog.tf` | Glue database `macro` as the Iceberg catalogue; an Athena workgroup with a 10 GB per-query scan cap. |
| `compute.tf` | ECR repository, ECS cluster, Fargate task (image from `../Dockerfile`) that syncs `raw/`, runs `make pull` and syncs back, EventBridge Scheduler at 07:30 UK time, CloudWatch logs, SNS alerts when a run exits non-zero. |
| `iam.tf` | Least privilege: the task reads and writes only `raw/` and `warehouse/` and only tables in `macro`; the scheduler may start only this task. |

```bash
cd terraform
terraform init
terraform plan -var 'subnet_ids=["subnet-..."]' -var 'security_group_ids=["sg-..."]' -var 'alert_email=you@example.com'
```

CI runs `terraform fmt -check`, `terraform init -backend=false` and `terraform validate` on every push. Nothing is applied
from CI: that needs an AWS account and credentials. The pipeline switches to this setup with `LAKEHOUSE_CATALOG=glue` and
`LAKEHOUSE_WAREHOUSE=s3://<bucket>/warehouse`; the code path is otherwise identical to the local SQLite catalogue.
