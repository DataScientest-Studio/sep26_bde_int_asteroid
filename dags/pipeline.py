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

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule
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
    schedule=None,
    #schedule="0 10 * * *",
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

    # ML

    create_dataset = BashOperator(
        task_id="create_dataset",
        bash_command="python3 /opt/airflow/src/ml/dataset.py",
    )

    train_model = BashOperator(
        task_id="train_model",
        bash_command="python3 /opt/airflow/src/ml/train.py",
    )

    make_predictions = BashOperator(
        task_id="make_predictions",
        bash_command="python3 /opt/airflow/src/ml/predict.py",
    )

    score_model = BashOperator(
        task_id="score_model",
        bash_command="python3 /opt/airflow/src/ml/score.py",
    )

    # Task

    (
        feed_mongo
        >> clean_mongo
        >> feed_postgres
        >> create_dataset
        >> train_model
        >> make_predictions
        >> score_model
    )
