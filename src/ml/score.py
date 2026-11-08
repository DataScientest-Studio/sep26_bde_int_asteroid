"""
This scores every currently-listed object and writes the result to ml_predictions table.
"""

import os
from datetime import date
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from predict import predict_listed, model_info

PATH = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PATH, "..", "..", ".env"))

host = os.getenv("PG_HOST")
username = os.getenv("PG_USER")
password = os.getenv("PG_PASSWORD")
port = os.getenv("PG_PORT")
database = os.getenv("PG_DB")

engine = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}")


def main():
    today = date.today()

    rows = predict_listed()
    rows["scored_on"] = today
    rows["was_listed"] = True
    rows["model_trained_at"] = model_info().get("trained_at")

    with engine.begin() as conn:
        conn.execute(text("delete from ml_predictions where scored_on = :d"), {"d": today})

    rows.to_sql("ml_predictions", engine, if_exists="append", index=False)

    print("Scored %d listed objects on %s" % (len(rows), today))
    print("Highest: %.4f   Lowest: %.4f" % (rows["probability_removed"].max(), rows["probability_removed"].min()))


if __name__ == "__main__":
    main()