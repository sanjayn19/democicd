"""Sample customer-ingestion DAG for promotion testing."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def extract_customer_batch() -> None:
    print("Extracting customer batch")


def validate_customer_batch() -> None:
    print("Validating customer batch")


with DAG(
    dag_id="customer_ingestion",
    description="Loads and validates a sample customer batch",
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",
    catchup=False,
    tags=["demo", "customer"],
) as dag:
    extract = PythonOperator(
        task_id="extract_customer_batch",
        python_callable=extract_customer_batch,
    )
    validate = PythonOperator(
        task_id="validate_customer_batch",
        python_callable=validate_customer_batch,
    )

    extract >> validate

