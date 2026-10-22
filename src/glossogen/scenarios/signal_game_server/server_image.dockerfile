# The shared server of signal_game_server: Debian with the tools the
# players and the judge use beyond coreutils. The player accounts are created when
# the container starts, from the scenario's agent ids, so the image names none.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends inotify-tools tree procps \
    && rm -rf /var/lib/apt/lists/*

# The container lives while its stdin is open: the simulation holds the pipe.
CMD ["sh", "-c", "cat > /dev/null"]
