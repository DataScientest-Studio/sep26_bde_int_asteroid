import os
import sys

PATH = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.dirname(PATH)
for folder in [PATH, SOURCE, os.path.join(SOURCE, 'ml'), os.path.join(SOURCE, 'dashboard')]:
    if folder not in sys.path:
        sys.path.insert(0, folder)

from fastapi import FastAPI # noqa: E402
from fastapi.middleware.cors import CORSMiddleware # noqa: E402
from routes import router # noqa: E402
from prometheus_fastapi_instrumentator import Instrumentator # noqa: E402


asteroid = FastAPI(
    title='Asteroid Risk Tracker',
    description=('NASA/JPL tracks asteroids and only displays their current risk list, not its historical day-by-day changes.\n '
                 '\nWe track the daily evolution of asteroid risk lists by comparing JPL data snapshots.\n ' 
                 '\nWe identify patterns and score newly listed asteroids based on their likelihood of remaining on the risk list.'),
    version="1.0.0",
    )

asteroid.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

Instrumentator(should_group_status_codes=False).instrument(asteroid).expose(asteroid)

asteroid.include_router(router)

