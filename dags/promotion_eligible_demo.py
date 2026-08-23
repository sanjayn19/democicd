"""Temporary test DAG that is eligible for PTEST promotion."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def publish_promotion_marker() -> None:
    print("Eligible selective-promotion test marker")


with DAG(
    dag_id="promotion_eligible_demo",
    description="Temporary eligible DAG for selective-promotion testing",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["demo", "promotion-test", "eligible"],
) as dag:
    publish = PythonOperator(
        task_id="publish_promotion_marker",
        python_callable=publish_promotion_marker,
    )
