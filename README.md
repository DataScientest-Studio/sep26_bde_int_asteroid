Asteroid Risk Tracker
==============================

NASA/JPL keeps track of every known asteroid and works out which ones will pass close to Earth. It also keeps a "risk list" of objects with some chance of hitting Earth. As telescopes gather more observations of an asteroid, its orbit is calculated more precisely, so objects get added to the risk list and, get removed from it once the uncertainty shrinks. JPL's website shows only today's situation. There is no public record of how the risk list changed day by day. If an object was on the list last month and is gone now, that story isn't stored anywhere.

This project builds a pipeline that collects asteroid data daily (including pulling years of past data to start), and storing every response exactly as received. Compare each day's data to the day before to automatically detect what changed - new objects, removed objects, updated risk estimates - and build a timeline per object. Train a model on already-resolved cases (removed vs. still-listed) to predict how risky newly added objects are likely to be. Expose all of this through visual dashboards and a web API so others can query it too. Automate the whole daily cycle so it runs unattended, with alerts if something breaks.


Project Organization
------------

    ├── LICENSE
    ├── README.md                   <- First thing to read to understand the concept and structure
    ├── data                        <- Contains data in JSON format
    │   ├── raw                         <- The original, immutable data dump.
    │   └── samples                     <- Sample data
    │
    |
    ├── logs                        <- Logs from scheduled run to fetch data
    |    └── fetch.log               
    │ 
    |   
    ├── notebooks                   <- Jupyter notebooks used to explore
    │   ├── eda.ipynb                   <- Data exploration
    |   └── Modelling.ipynb             <- Modelling for machine learning algorithm                
    │                         
    │
    ├── docs                        <- Documentation aiding understanding project
    │   ├── exploring_for_schema.txt    <- Explores MongoDB to reach decisions about Postgres DB        
    │   ├── glossary.txt                <- Orbital mechanics terms and their meaning
    │   └── psql_schema.txt             <- Logic behind each Postgres table
    |   
    |
    |── src/                        <- Core source code
    │   ├── ingest/                     <- Pipeline that is runs as scheduled 
    │   |    ├── fetch_data.py              <- Fetches raw data from JPL APIs
    │   |    ├── feed_mongo.py              <- Feeds raw data to MongoDB
    │   |    ├── clean_mongo.py             <- Cleans and formats json data in MongoDB
    │   |    └── feed_postgres.py           <- Cleaned data fed into Postgres tables
    │   |
    |   ├── sql/                    <- Queries
    │   |    ├── pg_schema.sql          <- DDL for structured and cleaned data
    │   |    ├── dataset.sql            <- Labeled row per listed object                         
    │   |    └── ml_predictions.sql     <- DDL for the predictions log
    |   |
    |   ├── ml/                     <- Machine learning model building
    │   |    ├── dataset.py             <- Reads and runs sql/dataset.sql. Returns a dataframe
    │   |    ├── train.py               <- Trains and fits ML model
    │   |    ├── model.joblib           <- The fitted pipeline with preprocessing 
    │   |    ├── features.json          <- The columns that predict.py validates against
    │   |    ├── metrics.json           <- What the model scored
    │   |    └── predict.py             <- Predicts objects with probability                        
    │   |
    |   ├── dashboard/
    │   │    ├── analytics.py       <- Statistics that feed into respective APIs
    │   │    └── app.py             <- Streamlit. Calls the API over HTTP.
    │   │
    │   └── api/
    │       ├── main.py             <- FastAPI app
    │       └── routes.py           <- Endpoints for API. Calls analytics.py and predict.py.
    |
    |
    └── requirements.txt            <- The requirements file for reproducing the analysis 
   

    
