-- This table must NOT be in pg_schema.sql.
-- It also must NOT be in feed_postgres.py's ALL_TABLES.
-- Because the daily rebuild would erase the required history.

create table if not exists ml_predictions (
    spkid bigint not null,
    pdes text,
    scored_on date not null,
    probability_removed double precision not null,
    was_listed boolean not null,
    model_trained_at text,
    primary key (spkid, scored_on)
);