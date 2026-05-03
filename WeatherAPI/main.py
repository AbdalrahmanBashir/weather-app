# This repesent the main file of the project,
# Where we will be using the FastAPI framework to create a web application
# That will allow us to get the weather information of a city.

# We will be using the openweathermap API to get the weather information of a city.
# We will be using redis to cache the weather information of a city for 1 hour,
# To reduce the number of API calls to the openweathermap API.

# imprt the necessary libraries
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import redis.asyncio as redis
import os
from dotenv import load_dotenv
import json
import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import httpx
from contextlib import asynccontextmanager

# Load env from project root
load_dotenv()
# Define the FastAPI app and the lifespan context manager to manage the lifecycle of the http client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.http_client = httpx.AsyncClient(timeout=5.0)

    yield

    # Shutdown
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)

# create a redis client
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True
)


# create a prometheus counter to count the number of http requests
http_request_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
)

# create a prometheus histogram to measure the duration of http requests
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'Duration of HTTP requests in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

# create a prometheus counter to count the number of http errors
http_errors_total = Counter(
    'http_errors_total',
    'Total HTTP errors',
    ['method', 'endpoint', 'status_code'],
)

# create a prometheus counter to count the number of failures from the openweathermap API
openweather_geo_api_errors_total = Counter(
    "openweather_geo_api_errors_total",
    "Failures from OpenWeather Geocoding API"
)

# create a prometheus counter to count the number of failures from the openweathermap API
openweather_weather_api_errors_total = Counter(
    "openweather_weather_api_errors_total",
    "Failures from OpenWeather Weather API"
)

# create a prometheus counter to count the number of redis connectivity failures
redis_failures_total = Counter(
    "redis_failures_total",
    "Redis connectivity failures"
)

# create a pydantic model for the request body


class WeatherRequest(BaseModel):
    city: str


def normalize_endpoint(path: str) -> str:
    """
    Normalize the endpoint path by replacing dynamic segments with placeholders.
    """
    return path.split("?")[0]


# Create a middleware to measure the duration of http requests and count the number of http requests and errors
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        # Skip metrics endpoint to avoid recursion
        return await call_next(request)
    method = request.method
    endpoint = normalize_endpoint(request.url.path)
    start_time = time.perf_counter()
    status_code = 500  # Default to 500 in case of unhandled exceptions
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        return response
    except Exception:
        raise
    finally:
        duration = time.perf_counter() - start_time
        http_request_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)
        if status_code.startswith("4") or status_code.startswith("5"):
            http_errors_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()

# create a route to expose the prometheus metrics


@app.get("/metrics")
async def metrics():
    """
    Expose Prometheus metrics.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Health check endpoints


@app.get("/health/live")
async def liveness_check():
    """
    Liveness Probe: Tells K8s if the app is alive. 
    If this fails, K8s will restart the container.
    """
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness_check():
    """
    Readiness Probe: Tells K8s if the app is ready to serve traffic.
    If this fails, K8s will stop sending traffic to the container until it passes.
    """
    try:
        if not await redis_client.ping():
            raise Exception("Redis ping failed")
    except Exception as e:
        redis_failures_total.inc()
        raise HTTPException(
            status_code=503, detail="Redis unreachable")
    if not os.getenv("OPENWEATHERMAP_API_KEY"):
        raise HTTPException(
            status_code=503, detail="OpenWeatherMap API key not set")
    return {"status": "ready"}

# create a route to get the weather information of a city


@app.post("/weather")
async def get_weather(request: WeatherRequest):
    """
    Get the weather information of a city.
    The weather information will be cached for 1 hour to reduce the number of API calls to the openweathermap API.
    If the weather information of the city is in the cache, it will be returned from the cache. 
    Otherwise, it will be fetched from the openweathermap API and then cached for future requests.
    The response will include the weather information and the source of the data (cache or API).
    """
    city_name = request.city.strip().lower()
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: missing OpenWeatherMap API key"
        )
    # check if the weather information of the city is in the cache
    try:
        cached_data = await redis_client.get(city_name)
    except Exception:
        redis_failures_total.inc()
        cached_data = None  # cache miss fallback

    if cached_data:
        return {"weather": json.loads(cached_data), "source": "cache"}

    # Get coordinates from city name
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={api_key}"
    client = request.app.state.http_client
    try:
        geo_response = await client.get(geo_url)
    except httpx.TimeoutException:
        openweather_geo_api_errors_total.inc()
        raise HTTPException(
            status_code=504, detail="External API unreachable")
    except httpx.RequestError:
        openweather_geo_api_errors_total.inc()
        raise HTTPException(status_code=502, detail="External API unreachable")

    if geo_response.status_code != 200:
        openweather_geo_api_errors_total.inc()
        raise HTTPException(status_code=404, detail="City not found")

    geo_data = geo_response.json()
    if not geo_data:
        raise HTTPException(status_code=404, detail="City not found")

    lat = geo_data[0]['lat']
    lon = geo_data[0]['lon']

    # if not in cache, get the weather information from the openweathermap API
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    try:
        response = await client.get(url)
    except httpx.TimeoutException:
        openweather_weather_api_errors_total.inc()
        raise HTTPException(
            status_code=504, detail="External API unreachable")

    if response.status_code == 404:  # ignore user input errors, as they are not our fault
        raise HTTPException(status_code=404, detail="City not found")

    if response.status_code >= 500:  # treat server errors as external API failures
        openweather_weather_api_errors_total.inc()
        raise HTTPException(
            status_code=502, detail="Upstream weather service failure")

    weather_data = response.json()
    city_info = geo_data[0]
    weather_info = {
        "description": weather_data['weather'][0]['description'],
        "temperature": f"{weather_data['main']['temp']}°C",
        "humidity": f"{weather_data['main']['humidity']}%",
        "city_full_name": f"{city_info['name']}, {city_info['country']}"
    }

    # cache the weather information for 1 hour
    await redis_client.setex(city_name, 3600, json.dumps(weather_info))

    return {"weather": weather_info, "source": "API"}
