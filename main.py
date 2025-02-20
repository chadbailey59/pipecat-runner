#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat Cloud Bot Server Implementation.

This FastAPI server is an MVP of sorts for Pipecat Cloud web clients. It has two important endpoints:
- POST /connect: Point an RTVI-compatible frontend at this endpoint to connect to a bot.
- GET /direct: Direct browser access to a bot via Daily Prebuilt.

The API also serves anything in /public, so you can include simple web clients there.

Requirements:
- Daily API key (set in .env file)
- Python 3.10+
- FastAPI
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Dict

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pipecat.transports.services.helpers.daily_rest import (
    DailyRESTHelper,
    DailyRoomParams,
)

# Load environment variables from .env file
load_dotenv(override=True)

# Maximum number of bot instances allowed per room
MAX_BOTS_PER_ROOM = 1

# Dictionary to track bot processes: {pid: (process, room_url)}
bot_procs = {}

# Store Daily API helpers
daily_helpers = {}


def cleanup():
    """Cleanup function to terminate all bot processes.

    Called during server shutdown.
    """
    for entry in bot_procs.values():
        proc = entry[0]
        proc.terminate()
        proc.wait()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager that handles startup and shutdown tasks.

    - Creates aiohttp session
    - Initializes Daily API helper
    - Cleans up resources on shutdown
    """
    aiohttp_session = aiohttp.ClientSession()
    daily_helpers["rest"] = DailyRESTHelper(
        daily_api_key=os.getenv("DAILY_API_KEY", ""),
        daily_api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
        aiohttp_session=aiohttp_session,
    )
    yield
    await aiohttp_session.close()
    cleanup()


# Initialize FastAPI app with lifespan manager
app = FastAPI(lifespan=lifespan)

# Configure CORS to allow requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def create_room_and_token() -> tuple[str, str]:
    """Helper function to create a Daily room and generate an access token.

    Returns:
        tuple[str, str]: A tuple containing (room_url, token)

    Raises:
        HTTPException: If room creation or token generation fails
    """
    room = await daily_helpers["rest"].create_room(DailyRoomParams())
    if not room.url:
        raise HTTPException(status_code=500, detail="Failed to create room")

    token = await daily_helpers["rest"].get_token(room.url)
    if not token:
        raise HTTPException(status_code=500, detail=f"Failed to get token for room: {room.url}")

    return room.url, token


async def start_bot() -> tuple[str, str]:
    """Start a bot process."""
    # room_url = os.getenv("DAILY_SAMPLE_ROOM_URL")
    # token = os.getenv("DAILY_SAMPLE_ROOM_TOKEN")
    # if not room_url:
    #     print("Creating room")
    #     room_url, token = await create_room_and_token()
    #     print(f"Room URL: {room_url}")

    # THIS IS WHERE we start a bot process
    aiohttp_session = aiohttp.ClientSession()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('PCC_API_KEY')}",
    }
    params = {"createDailyRoom": True}
    print(f"Headers is {headers}, json is {params}")
    async with aiohttp_session.post(
        os.getenv("PCC_BOT_START_URL"), headers=headers, json=params
    ) as r:
        if r.status != 200:
            text = await r.text()
            raise Exception(f"Unable to create room (status: {r.status}): {text}")

        data = await r.json()
        room_url = data["dailyRoom"]
        token = data["dailyToken"]

    return (room_url, token)


@app.get("/direct")
async def start_agent(request: Request):
    """Endpoint for direct browser access to the bot.

    Creates a room, starts a bot instance, and redirects to the Daily room URL.

    Returns:
        RedirectResponse: Redirects to the Daily room URL

    Raises:
        HTTPException: If room creation, token generation, or bot startup fails
    """

    room_url, token = await start_bot()
    return RedirectResponse(room_url)


@app.post("/connect")
async def rtvi_connect(request: Request) -> Dict[Any, Any]:
    """RTVI connect endpoint that creates a room and returns connection credentials.

    This endpoint is called by RTVI clients to establish a connection.

    Returns:
        Dict[Any, Any]: Authentication bundle containing room_url and token

    Raises:
        HTTPException: If room creation, token generation, or bot startup fails
    """

    room_url, token = await start_bot()

    # Return the authentication bundle in format expected by DailyTransport
    return {"room_url": room_url, "token": token}


@app.get("/status/{pid}")
def get_status(pid: int):
    """Get the status of a specific bot process.

    Args:
        pid (int): Process ID of the bot

    Returns:
        JSONResponse: Status information for the bot

    Raises:
        HTTPException: If the specified bot process is not found
    """
    # Look up the subprocess
    proc = bot_procs.get(pid)

    # If the subprocess doesn't exist, return an error
    if not proc:
        raise HTTPException(status_code=404, detail=f"Bot with process id: {pid} not found")

    # Check the status of the subprocess
    status = "running" if proc[0].poll() is None else "finished"
    return JSONResponse({"bot_id": pid, "status": status})


app.mount("/", StaticFiles(directory="static", html=True), name="static")

# if __name__ == "__main__":
#     import uvicorn

#     # Parse command line arguments for server configuration
#     default_host = os.getenv("HOST", "0.0.0.0")
#     default_port = int(os.getenv("FAST_API_PORT", "7860"))

#     parser = argparse.ArgumentParser(description="annie hall weather bot FastAPI server")
#     parser.add_argument("--host", type=str, default=default_host, help="Host address")
#     parser.add_argument("--port", type=int, default=default_port, help="Port number")
#     parser.add_argument("--reload", action="store_true", help="Reload code on change")

#     config = parser.parse_args()

#     # Start the FastAPI server
#     uvicorn.run(
#         "server:app",
#         host=config.host,
#         port=config.port,
#         reload=config.reload,
#     )
