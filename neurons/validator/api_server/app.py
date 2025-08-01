# neurons/validator/api_server/app.py
import argparse
import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from neurons.validator.api_server.rate_limiter import limiter
from neurons.validator.api_server.routers import (
    miners,
    posts,
    interactions,
    accounts,
    content,
)


app = FastAPI(
    title="Nuance Network API",
    description="API for the Nuance Network decentralized social media validation system",
)

app.add_middleware(
    CORSMiddleware,
    # Origins that should be permitted to make cross-origin requests
    allow_origins=[
        "http://localhost:5173",  # Local development server
        "https://www.nuance.info",  # Production domain
        "https://www.docs.nuance.info",  # Documentation domain
        "https://docs.nuance.info",  # Documentation domain without www
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Include routers
app.include_router(miners.router)
app.include_router(posts.router)
app.include_router(interactions.router)
app.include_router(accounts.router)
app.include_router(content.router)


@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
        show_sidebar=True,
    )


async def run_api_server(port: int, shutdown_event: asyncio.Event) -> None:
    """
    Run the FastAPI server with uvicorn
    """
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Start the server task
    api_task = asyncio.create_task(server.serve())

    # Wait for shutdown event
    await shutdown_event.wait()

    # Stop the server
    server.should_exit = True
    await api_task


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # For direct execution during development
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=args.port)
