# Keep the deployed SDK, automation service and scientific runtime unchanged.
ARG RUNTIME_IMAGE=ghcr.io/openhands/agent-canvas:1.27.1@sha256:6f54e27c47c8073d402391495fa869afca807e9154f0d90bfe05f7ada6ec8ee3
FROM ${RUNTIME_IMAGE} AS frontend-build
USER root
WORKDIR /build
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG SOURCE_COMMIT
RUN node -e 'if (!/^[a-f0-9]{40}$/.test(process.env.SOURCE_COMMIT || "")) process.exit(1)'
ENV VITE_BASE_PATH=/canvas
RUN npm run make-i18n && npm run check-translation-completeness && npm run typecheck && npm run build
RUN node -e 'const fs = require("node:fs"); fs.writeFileSync("/build/release.json", JSON.stringify({source:"https://github.com/marvcks/EM-Agent",revision:process.env.SOURCE_COMMIT,canvasVersion:require("./package.json").version,nodeVersion:process.version}) + "\n")'

FROM ${RUNTIME_IMAGE} AS final
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.title="EM-Agent"
LABEL org.opencontainers.image.source="https://github.com/marvcks/EM-Agent"
LABEL org.opencontainers.image.revision="${SOURCE_COMMIT}"
LABEL io.em-agent.upstream.revision="f07aebdf5cdd71f4a05ebcf30f8bef5e4e3b70b9"
LABEL io.em-agent.magus="1"
LABEL io.em-agent.reactions="1"
LABEL io.em-agent.bde="1"
ENV AGENT_CANVAS_BUILD_GIT_SHA=${SOURCE_COMMIT}
ENV AGENT_CANVAS_BUILD_GIT_REF=${SOURCE_COMMIT}
USER root
RUN rm -rf /opt/agent-canvas/frontend
COPY --from=frontend-build /build/build /opt/agent-canvas/frontend
COPY --from=frontend-build /build/release.json /opt/em-agent/release.json
ENV EM_AGENT_SCIENCE_APPS=1
COPY docker/entrypoint.sh /opt/agent-canvas/entrypoint.sh
RUN chmod 755 /opt/agent-canvas/entrypoint.sh
COPY tools/science_apps/ /opt/agent-canvas/science_apps/
RUN install -m 755 /opt/agent-canvas/science_apps/magus-mace /usr/local/bin/magus-mace \
 && install -m 755 /opt/agent-canvas/science_apps/em-magus /usr/local/bin/em-magus \
 && install -m 755 /opt/agent-canvas/science_apps/aizynth-route /usr/local/bin/aizynth-route \
 && install -m 755 /opt/agent-canvas/science_apps/lcms-cf /usr/local/bin/lcms-cf \
 && install -m 755 /opt/agent-canvas/science_apps/em-reaction /usr/local/bin/em-reaction \
 && install -m 755 /opt/agent-canvas/science_apps/bde-analyze /usr/local/bin/bde-analyze \
 && install -m 755 /opt/agent-canvas/science_apps/em-bde /usr/local/bin/em-bde \
 && install -m 755 /opt/agent-canvas/science_apps/mineru-parse /usr/local/bin/mineru-parse \
 && install -m 755 /opt/agent-canvas/science_apps/em-mineru /usr/local/bin/em-mineru
USER openhands
