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

# PDF dependencies are independent of application revisions and remain cached.
FROM ${RUNTIME_IMAGE} AS pdf-runtime
USER root
ARG POPPLER_VERSION=25.03.0-5+deb13u4
RUN mkdir -p /opt/em-agent \
 && sed -e 's|http://snapshot.debian.org/archive/debian/[0-9TZ]*/|https://mirrors.tuna.tsinghua.edu.cn/debian/|' \
        -e 's|http://snapshot.debian.org/archive/debian-security/[0-9TZ]*/|https://mirrors.tuna.tsinghua.edu.cn/debian-security/|' \
        /etc/apt/sources.list.d/debian.sources > /tmp/em-agent-pdf.sources \
 && apt-get -o Dir::Etc::sourcelist=/tmp/em-agent-pdf.sources -o Dir::Etc::sourceparts=- -o Acquire::Retries=2 -o Acquire::https::Timeout=30 update \
 && apt-get -o Dir::Etc::sourcelist=/tmp/em-agent-pdf.sources -o Dir::Etc::sourceparts=- -o Acquire::Retries=2 -o Acquire::https::Timeout=30 install -y --no-install-recommends --no-upgrade "poppler-utils=${POPPLER_VERSION}" \
 && dpkg-query -W poppler-utils > /opt/em-agent/pdf-runtime.txt \
 && dpkg-query -W > /opt/em-agent/pdf-runtime-packages.tsv \
 && rm -rf /var/lib/apt/lists/* /tmp/em-agent-pdf.sources

FROM pdf-runtime AS cnt2d-runtime
USER root
RUN sed -e 's|http://snapshot.debian.org/archive/debian/[0-9TZ]*/|https://mirrors.tuna.tsinghua.edu.cn/debian/|' \
        -e 's|http://snapshot.debian.org/archive/debian-security/[0-9TZ]*/|https://mirrors.tuna.tsinghua.edu.cn/debian-security/|' \
        /etc/apt/sources.list.d/debian.sources > /tmp/em-agent-cnt2d.sources \
 && apt-get -o Dir::Etc::sourcelist=/tmp/em-agent-cnt2d.sources -o Dir::Etc::sourceparts=- -o Acquire::Retries=2 update \
 && apt-get -o Dir::Etc::sourcelist=/tmp/em-agent-cnt2d.sources -o Dir::Etc::sourceparts=- install -y --no-install-recommends --no-upgrade libglu1-mesa \
 && dpkg-query -W > /opt/em-agent/cnt2d-runtime-packages.tsv \
 && rm -rf /var/lib/apt/lists/* /tmp/em-agent-cnt2d.sources

FROM cnt2d-runtime AS final
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.title="EM-Agent"
LABEL org.opencontainers.image.source="https://github.com/marvcks/EM-Agent"
LABEL org.opencontainers.image.revision="${SOURCE_COMMIT}"
LABEL io.em-agent.upstream.revision="f07aebdf5cdd71f4a05ebcf30f8bef5e4e3b70b9"
LABEL io.em-agent.magus="1"
LABEL io.em-agent.reactions="1"
LABEL io.em-agent.bde="1"
LABEL io.em-agent.crystal-morphology="1"
LABEL io.em-agent.analysis="1"
LABEL io.em-agent.cnt2d="1"
ENV AGENT_CANVAS_BUILD_GIT_SHA=${SOURCE_COMMIT}
ENV AGENT_CANVAS_BUILD_GIT_REF=${SOURCE_COMMIT}
USER root
RUN rm -rf /opt/agent-canvas/frontend
COPY --from=frontend-build /build/build /opt/agent-canvas/frontend
COPY --from=frontend-build /build/release.json /opt/em-agent/release.json
ENV EM_AGENT_SCIENCE_APPS=1
COPY docker/entrypoint.sh /opt/agent-canvas/entrypoint.sh
COPY scripts/runtime-services-info.mjs /opt/agent-canvas/runtime-services-info.mjs
COPY tools/em_agent_runtime/ /opt/agent-canvas/em_agent_runtime/
RUN mv /usr/local/bin/claude-agent-acp /usr/local/bin/claude-agent-acp.upstream \
 && install -m 755 /opt/agent-canvas/em_agent_runtime/claude-agent-acp /usr/local/bin/claude-agent-acp \
 && install -m 755 /opt/agent-canvas/em_agent_runtime/em-env /usr/local/bin/em-env \
 && ln -s /opt/agent-canvas/em_agent_runtime/task-shell.sh /etc/profile.d/em-agent-analysis.sh \
 && printf '\n. /opt/agent-canvas/em_agent_runtime/task-shell.sh\n' >> /etc/bash.bashrc
RUN chmod 755 /opt/agent-canvas/entrypoint.sh
COPY tools/science_apps/ /opt/agent-canvas/science_apps/
COPY CNT2D_COMSOL_20260930/python/cnt2d/ /opt/agent-canvas/science_apps/cnt2d/
RUN install -m 755 /opt/agent-canvas/science_apps/magus-mace /usr/local/bin/magus-mace \
 && install -m 755 /opt/agent-canvas/science_apps/em-magus /usr/local/bin/em-magus \
 && install -m 755 /opt/agent-canvas/science_apps/aizynth-route /usr/local/bin/aizynth-route \
 && install -m 755 /opt/agent-canvas/science_apps/lcms-cf /usr/local/bin/lcms-cf \
 && install -m 755 /opt/agent-canvas/science_apps/em-reaction /usr/local/bin/em-reaction \
 && install -m 755 /opt/agent-canvas/science_apps/bde-analyze /usr/local/bin/bde-analyze \
 && install -m 755 /opt/agent-canvas/science_apps/em-bde /usr/local/bin/em-bde \
 && install -m 755 /opt/agent-canvas/science_apps/mineru-parse /usr/local/bin/mineru-parse \
 && install -m 755 /opt/agent-canvas/science_apps/em-mineru /usr/local/bin/em-mineru \
 && install -m 755 /opt/agent-canvas/science_apps/morphology-classify /usr/local/bin/morphology-classify \
 && install -m 755 /opt/agent-canvas/science_apps/em-morphology /usr/local/bin/em-morphology \
 && install -m 755 /opt/agent-canvas/science_apps/cnt2d-solve /usr/local/bin/cnt2d-solve \
 && install -m 755 /opt/agent-canvas/science_apps/em-cnt2d /usr/local/bin/em-cnt2d
USER openhands
