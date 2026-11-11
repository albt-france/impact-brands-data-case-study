"""Load the SIMULATED raw Parquet files into BigQuery (dataset `raw`), so that the same dbt project
runs with `dbt build --target bigquery`. Works with the free BigQuery sandbox.

Needs: pip install google-cloud-bigquery, and either
  gcloud auth application-default login   (recommended)
or GOOGLE_APPLICATION_CREDENTIALS pointing to a service-account key file (kept out of Git, see .env.example).

Usage: python src/load_bigquery.py
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

PROJECT = os.environ.get("GCP_PROJECT_ID", "impact-brands-case-study")
LOCATION = os.environ.get("GCP_LOCATION", "EU")
DATASET = "raw"


def main():
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    client.create_dataset(bigquery.Dataset(f"{PROJECT}.{DATASET}"), exists_ok=True)
    job_config = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET,
                                        write_disposition="WRITE_TRUNCATE")
    for file in sorted((ROOT / "data" / "simulated").glob("raw_*.parquet")):
        table_id = f"{PROJECT}.{DATASET}.{file.stem}"
        with file.open("rb") as handle:
            client.load_table_from_file(handle, table_id, job_config=job_config).result()
        print(f"loaded {table_id}: {client.get_table(table_id).num_rows:,} rows")


if __name__ == "__main__":
    main()
