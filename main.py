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
from typing import Any, Dict

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

# Load environment variables from .env file
load_dotenv(override=True)


# Initialize FastAPI app with lifespan manager
app = FastAPI()

# Configure CORS to allow requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def start_bot() -> tuple[str, str]:
    """Start a bot process."""
    aiohttp_session = aiohttp.ClientSession()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('PCC_API_KEY')}",
    }
    params = {"createDailyRoom": True}
    async with aiohttp_session.post(
        os.getenv("PCC_BOT_START_URL"), headers=headers, json=params
    ) as r:
        if r.status != 200:
            text = await r.text()
            raise Exception(f"Unable to create room (status: {r.status}): {text}")

        data = await r.json()
        room_url = data["dailyRoom"]
        token = data["dailyToken"]
        await aiohttp_session.close()
    print(f"Returning room: {room_url} and token: {token}")
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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
