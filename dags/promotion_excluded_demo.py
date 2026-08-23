"""Temporary test DAG that must remain out of PTEST."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def publish_exclusion_marker() -> None:
    print("Non-promoted selective-promotion test marker")


with DAG(
    dag_id="promotion_excluded_demo",
    description="Temporary excluded DAG for selective-promotion testing",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["demo", "promotion-test", "excluded"],
) as dag:
    publish = PythonOperator(
        task_id="publish_exclusion_marker",
        python_callable=publish_exclusion_marker,
    )
