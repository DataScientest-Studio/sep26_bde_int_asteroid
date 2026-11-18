set -euo pipefail

echo "START POSTGRES"
docker compose up -d --wait postgres

echo "INITIATE METADATA DATABASE"
docker compose exec -T postgres psql -U asteroid -d asteroid -c "CREATE DATABASE airflow OWNER asteroid;" || echo "DATABASE already exists, continuing"

echo "DIRECTORIES"
mkdir -p dags airflow-logs

echo "BUILDING AIRFLOW"
docker compose build airflow-init

echo "INITIALISING AIRFLOW"
docker compose up -d airflow-init

code=$(docker wait asteroid-airflow-init)
if [ "$code" != "0" ]; then
    echo "airflow-init failed with exit code $code"
    docker compose logs airflow-init
    exit 1
fi

echo "STARTING SCHEDULER AND WEBSERVER"
docker compose up -d airflow-scheduler airflow-webserver

echo "WAITING FOR WEBSERVER"
for i in $(seq 1 60); do
    if curl -sf -o /dev/null localhost:8080/health; then
        break
    fi
    sleep 2
done

curl -sf localhost:8080/health
echo
echo
echo "  Airflow:  http://localhost:8080   (asteroid / asteroid)"
echo
