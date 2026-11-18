set -euo pipefail

echo "STARTING DATABASES"
docker compose up -d --wait postgres mongo

echo "SHOW SCHEMA"
docker compose exec -T postgres psql -U asteroid -d asteroid -c "\dt"

echo "LOADING RAW DATA"

python3 src/ingest/feed_mongo.py
python3 src/ingest/clean_mongo.py
python3 src/ingest/feed_postgres.py

echo "STARTING APPLICATION"
docker compose up -d --build api dashboard

echo "WAITING FOR THE APPLICATION"
for i in $(seq 1 30); do
    if curl -sf -o /dev/null localhost:8501/_stcore/health; then
        break
    fi
    sleep 1
done

curl -sf localhost:8000/health
echo
echo
echo "  Dashboard:  http://localhost:8501"
echo "  API docs:   http://localhost:8000/docs"
echo