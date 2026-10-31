"""
This file reads the 'src/sql/dataset.sql' and returns the result in the form of a DataFrame.
Here we include a function named 'load_data' which can be called when building a ML model.
"""

import os
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

PY_FILE = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(PY_FILE, "..", "sql", "dataset.sql")
ENV_FILE = os.path.join(PY_FILE, "..", "..", ".env")

load_dotenv(ENV_FILE)

host = os.getenv('PG_HOST')
username = os.getenv('PG_USER')
password = os.getenv('PG_PASSWORD')
port = os.getenv('PG_PORT')
database = os.getenv('PG_DB')

engine_url = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}")

def load_data():
    sql = open(SQL_FILE).read()
    engine = engine_url
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
    finally:
        engine.dispose()
    return df

if __name__ == "__main__":
    df = load_data()
    print("Number of rows and columns are: ", df.shape)
    print("\nColumns: ", list(df.columns))