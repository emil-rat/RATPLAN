# RATPLAN's ITWOM service — GPL-2.0. See LICENSE and README.md.
#
# Builds unmodified upstream SPLAT! (which bundles itwom3.0.cpp) from source
# and wraps it with a minimal JSON-over-stdio CLI. This image, and the SPLAT!
# source it contains, are GPL-2.0. RATPLAN's own code never runs inside this
# image or links against anything here — it only invokes this container as a
# subprocess (`docker run -i`) and exchanges JSON over stdin/stdout, per
# architecture.md §3.1.

FROM debian:bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make git libbz2-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
# Pinned to a specific commit for reproducibility — update deliberately, not
# by floating on a branch, since this is GPL-2.0 third-party source.
RUN git clone https://github.com/jmcmellen/splat.git splat && \
    cd splat && git checkout 08f06f56470a8361a5609503a6b1cb02f07f48dc

WORKDIR /src/splat
RUN chmod +x build utils/build && ./build splat

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libbz2-1.0 python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /src/splat/splat /usr/local/bin/splat
COPY --from=build /src/splat/COPYING /usr/share/doc/splat/COPYING

COPY wrapper/itwom_cli.py /usr/local/bin/itwom_cli.py
RUN chmod +x /usr/local/bin/itwom_cli.py

ENTRYPOINT ["python3", "/usr/local/bin/itwom_cli.py"]
