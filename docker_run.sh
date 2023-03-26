#!/bin/bash

# Build the Docker image
docker build -t tee-time-bot .

# Run the Docker container with the specified name, restart policy, and environment file
docker run -d --name tee-time-bot --restart unless-stopped --env-file .env tee-time-bot
