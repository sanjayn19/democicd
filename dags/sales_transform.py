"""Sample sales transformation DAG for promotion testing."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def stage_sales() -> None:
    print("Staging sales data")


def transform_sales() -> None:
    print("Transforming staged sales data")


with DAG(
    dag_id="sales_transform",
    description="Stages and transforms sample sales data",
    start_date=datetime(2026, 1, 1),
    schedule="30 3 * * *",
    catchup=False,
    tags=["demo", "sales"],
) as dag:
    stage = PythonOperator(task_id="stage_sales", python_callable=stage_sales)
    transform = PythonOperator(
        task_id="transform_sales",
        python_callable=transform_sales,
    )

    stage >> transform

