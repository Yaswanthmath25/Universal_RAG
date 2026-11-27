# SnapDeploy demo setup

This repository can be deployed as two SnapDeploy containers: the FastAPI
backend from `main` and Streamlit from the `snapdeploy-frontend` branch. Both
Dockerfiles target the platform's ARM64 containers. The backend uses local
Chroma; it does not require a Chroma service or API key.

## 1. Deploy the backend

Create a container from this GitHub repository, select branch `main`, and use
the repository root as its root directory. SnapDeploy will build the root
`Dockerfile` and detect the backend port from the injected `PORT` variable.

Set these runtime variables on the backend container:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Your existing PostgreSQL connection URL |
| `SECRET_KEY` | A long, random secret used to sign login tokens |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | A token with Workers AI read and edit permissions |
| `CHROMA_PATH` | `/app/chroma_db` |

`ALGORITHM` and `ACCESS_TOKEN_EXPIRE_MINUTES` are optional; the backend defaults
to `HS256` and 60 minutes.

The PostgreSQL database must be reachable from SnapDeploy. SnapDeploy's free
tier does not include a database.

## 2. Deploy the frontend

SnapDeploy links a repository branch to one container, so use the
`snapdeploy-frontend` branch for the second container. Set its root directory
to `frontend`; the `frontend/Dockerfile` runs Streamlit.

Set this runtime variable on the frontend container:

| Variable | Value |
| --- | --- |
| `API_URL` | The backend container's HTTPS URL, for example `https://your-api.containers.snapdeploy.app` |

After setting `API_URL`, redeploy the frontend.

## 3. Wake and demo

Free containers sleep after roughly 15 minutes without traffic. Before each
demo, open the backend container URL in a browser and wait for it to wake; then
open the frontend URL. Upload your demo documents again after a wake or
redeploy because SnapDeploy has no persistent disk on the free tier.

The free tier provides 100 running container-hours per month across the
account. With both containers awake for one hour, that uses about two
container-hours. Each container has 512 MB RAM, so the backend may still run
out of memory despite the lightweight retrieval implementation in this repo.

Cloudflare Workers AI also has its own free daily usage limit. OpenAI is not
used by the backend's AI flows.
