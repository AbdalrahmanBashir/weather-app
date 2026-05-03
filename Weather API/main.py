# This repesent the main file of the project,
# Where we will be using the flask framework to create a web application
# That will allow us to get the weather information of a city.

# We will be using the openweathermap API to get the weather information of a city.
# We will be using redis to cache the weather information of a city for 10 minutes
# To reduce the number of API calls to the openweathermap API.

# imprt the necessary libraries

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import requests
import redis
import os
from dotenv import load_dotenv
import json

# Load env from project root
load_dotenv()

# create a redis client
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True
)

# create a fastapi app
app = FastAPI()

# create a pydantic model for the request body


class WeatherRequest(BaseModel):
    city: str

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
        if not redis_client.ping():
            raise Exception("Redis ping failed")
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Redis unreachable: {str(e)}")
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
    # check if the weather information of the city is in the cache
    cached_data = redis_client.get(city_name)
    if cached_data:
        return {"weather": json.loads(cached_data), "source": "cache"}

    # Get coordinates from city name
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={api_key}"
    geo_response = requests.get(geo_url)
    if geo_response.status_code != 200:
        raise HTTPException(status_code=404, detail="City not found")

    geo_data = geo_response.json()
    if not geo_data:
        raise HTTPException(status_code=404, detail="City not found")

    lat = geo_data[0]['lat']
    lon = geo_data[0]['lon']

    # if not in cache, get the weather information from the openweathermap API
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="City not found")

    weather_data = response.json()
    city_info = geo_data[0]
    weather_info = {
        "description": weather_data['weather'][0]['description'],
        "temperature": f"{weather_data['main']['temp']}°C",
        "humidity": f"{weather_data['main']['humidity']}%",
        "city_full_name": f"{city_info['name']}, {city_info['country']}"
    }

    # cache the weather information for 1 hour
    redis_client.setex(city_name, 3600, json.dumps(weather_info))

    return {"weather": weather_info, "source": "API"}
