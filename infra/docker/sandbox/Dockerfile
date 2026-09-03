# Development sandbox for the coding agent. Non-root, /workspace only.
FROM debian:trixie-slim

# C++ toolchain (WP02): gcc AND clang (diagnostic divergence between the two is
# itself a useful signal, per blueprint/wp/WP02-cpp-toolchain.md §2), ninja +
# ccache as the default build path (B1/B2), clang-tidy/clang-format/clangd for
# static analysis and formatting, lld/gdb, and lcov/gcovr for coverage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl wget ca-certificates \
        build-essential cmake ninja-build ccache pkg-config \
        gcc g++ clang clangd clang-tidy clang-format lld gdb \
        lcov gcovr \
        python3 python3-pip python3-venv python3-dev \
        nodejs npm \
        jq ripgrep fd-find unzip zip tar \
    && rm -rf /var/lib/apt/lists/*

ARG SANDBOX_UID=10001
ARG SANDBOX_GID=10001
RUN groupadd -g "${SANDBOX_GID}" sandbox \
    && useradd -m -u "${SANDBOX_UID}" -g "${SANDBOX_GID}" -s /bin/bash sandbox

# vcpkg in manifest mode (blueprint §9): the toolchain is baked into the image,
# but package resolution/install still happens per-project from vcpkg.json at
# build time, using the binary cache mounted at /home/sandbox/.cache/vcpkg
# (see infra/docker/compose.yaml when the sandbox service is wired up in WP08).
ENV VCPKG_ROOT=/opt/vcpkg
RUN git -c http.version=HTTP/1.1 clone --depth 1 \
        https://github.com/microsoft/vcpkg.git "${VCPKG_ROOT}" \
    && "${VCPKG_ROOT}/bootstrap-vcpkg.sh" -disableMetrics \
    && chmod -R a+rX "${VCPKG_ROOT}"
ENV PATH="${VCPKG_ROOT}:${PATH}"

# ccache: never silently disabled, always the default compiler front-end.
ENV CCACHE_DIR=/home/sandbox/.cache/ccache
ENV PATH="/usr/lib/ccache:${PATH}"

WORKDIR /workspace
RUN chown sandbox:sandbox /workspace
USER sandbox

COPY --chown=sandbox:sandbox entrypoint.sh /usr/local/bin/entrypoint.sh
USER root
RUN chmod +x /usr/local/bin/entrypoint.sh
USER sandbox

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

