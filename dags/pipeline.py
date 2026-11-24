"""
This pipeline does NOT fetch the raw data from JPL API.
That part is done by launchd/systemd scheduled for daily and weekly.
    - daily: sentry_s, sentry_r
    - weekly: cad, sbdb

This code instead provides a DAG for the rest of the data pipeline:
    - read from storage
    - transform
    - prepare for consumption
"""

from datetime import timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
import pendulum

default_args = {
    "owner": "asteroid",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="asteroid_pipeline",
    description="Loads raw data into MongoDB and PostgreSQL and score objects using ML",
    default_args=default_args,
    start_date=pendulum.datetime(2026, 11, 1, tz="Europe/Berlin"),
    schedule="30 9 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["asteroid"],
) as dag:

    # Ingestion

    feed_mongo = BashOperator(
        task_id="feed_mongo",
        bash_command="python3 /opt/airflow/src/ingest/feed_mongo.py",
    )

    clean_mongo = BashOperator(
        task_id="clean_mongo",
        bash_command="python3 /opt/airflow/src/ingest/clean_mongo.py",
    )

    feed_postgres = BashOperator(
        task_id="feed_postgres",
        bash_command="python3 /opt/airflow/src/ingest/feed_postgres.py",
    )

    # Task

    feed_mongo >> clean_mongo >> feed_postgres