# Linux container image (alternative to the Windows installer). Build from the ITAM folder:
#   docker build -f deploy/docker/Dockerfile -t itam .
FROM node:22-alpine AS web
WORKDIR /src/Frontend
COPY Frontend/package*.json ./
RUN npm ci
COPY Frontend/ ./
RUN mkdir -p ../Backend/ITAM.Api && npm run build

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props ITAM.slnx ./
COPY Backend/ Backend/
COPY --from=web /src/Backend/ITAM.Api/wwwroot Backend/ITAM.Api/wwwroot
RUN dotnet publish Backend/ITAM.Api/ITAM.Api.csproj -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:10.0
# pg_dump/pg_restore for backups; fonts with Cyrillic for the built-in PDF renderer; LibreOffice is optional (large).
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client fonts-dejavu-core curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app .
ENV ITAM_DATA_ROOT=/data \
    ITAM_Server__Urls=http://0.0.0.0:8080
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fsS http://localhost:8080/health || exit 1
ENTRYPOINT ["dotnet", "ITAM.Server.dll"]
