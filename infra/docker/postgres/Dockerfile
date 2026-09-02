# pgvector is not in the default postgres image; build it in.
FROM postgres:16-bookworm

# http.version=HTTP/1.1 works around a git/libcurl HTTP2 bug that breaks smart-HTTP clones of github.com from this base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-16 \
        git \
        ca-certificates \
    && git -c http.version=HTTP/1.1 clone --branch v0.7.4 --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector \
    && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector \
    && apt-get purge -y build-essential postgresql-server-dev-16 git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY initdb/00-extensions.sql /docker-entrypoint-initdb.d/00-extensions.sql
COPY initdb/01-roles.sh /docker-entrypoint-initdb.d/01-roles.sh
RUN chmod +x /docker-entrypoint-initdb.d/01-roles.sh
