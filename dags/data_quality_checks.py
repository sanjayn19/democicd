"""Sample data-quality DAG for promotion testing."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def check_freshness() -> None:
    print("Checking source freshness")


def check_row_counts() -> None:
    print("Checking row-count thresholds")


with DAG(
    dag_id="data_quality_checks",
    description="Runs basic data quality checks",
    start_date=datetime(2026, 1, 1),
    schedule="0 5 * * *",
    catchup=False,
    tags=["demo", "quality"],
) as dag:
    freshness = PythonOperator(
        task_id="check_freshness",
        python_callable=check_freshness,
    )
    row_counts = PythonOperator(
        task_id="check_row_counts",
        python_callable=check_row_counts,
    )

    freshness >> row_counts

