import os
from dotenv import load_dotenv
import redis.asyncio as redis

load_dotenv(dotenv_path="../.env")

HOST = os.getenv("REDIS_HOST", "localhost")
PORT = os.getenv("REDIS_PORT", "6379")

# Create a global asynchronous Redis connection pool
redis_url = f"redis://{HOST}:{PORT}/0"
redis_db = redis.from_url(redis_url, decode_responses=True)
