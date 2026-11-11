ARG NODE_BASE
ARG PYTHON_BASE
FROM ${NODE_BASE} AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM ${PYTHON_BASE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --system wellspring && useradd --system --gid wellspring --no-create-home wellspring \
    && mkdir -p /app/.secrets && chown wellspring:wellspring /app/.secrets && chmod 700 /app/.secrets
COPY backend/wellspring ./wellspring
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY deploy/offline/runtime.py deploy/offline/permissions.py deploy/offline/combined_app.py ./
COPY --from=frontend /web/dist ./static
USER wellspring
EXPOSE 8000
ENTRYPOINT ["python", "runtime.py"]
CMD ["api"]
