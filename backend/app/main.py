from fastapi import FastAPI

app = FastAPI(
    title="OpsPilot Core API",
    version="0.1.0",
    description="AI-powered incident management and observability platform",
)


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "opspilot-backend",
        "version": "0.1.0",
    }
