# The shared server of signal_game's file_system medium: Debian with the tools the
# players and the judge use beyond coreutils. The player accounts are created when
# the container starts, from the scenario's agent ids, so the image names none.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends inotify-tools tree procps \
    && rm -rf /var/lib/apt/lists/*

CMD ["sleep", "infinity"]
