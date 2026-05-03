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

# Load env from project root
load_dotenv()

# create a redis client
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)))

# create a fastapi app
app = FastAPI()

# create a pydantic model for the request body


class WeatherRequest(BaseModel):
    city: str

# create a route to get the weather information of a city


@app.get("/health")
async def health_check():
    result = redis_client.ping()
    if not result:
        raise HTTPException(status_code=500, detail="Redis is not healthy")
    return {"status": "healthy"}


@app.post("/weather")
async def get_weather(request: WeatherRequest):
    # check if the weather information of the city is in the cache
    cached_weather = redis_client.get(request.city)
    if cached_weather:
        return {"weather": cached_weather.decode("utf-8"), "source": "cache"}

    # if not in cache, get the weather information from the openweathermap API
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={request.city}&appid={api_key}"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="City not found")

    weather_data = response.json()
    print(weather_data)
    weather_info = f"{weather_data['weather'][0]['description']}, {weather_data['main']['temp']}K"

    # cache the weather information for 1 hour
    redis_client.setex(request.city, 3600, weather_info)

    return {"weather": weather_info, "source": "API"}
