# The scheduled pull (terraform/compute.tf). Athena reads the Iceberg tables in S3; dbt runs locally or in CI.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends make && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "pyiceberg[glue,s3fs]" awscli
COPY . .
CMD ["make", "pull"]
