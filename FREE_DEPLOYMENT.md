# Low-cost deployment setup

The backend runs Chroma locally in persistent-client mode. It does not connect
to Chroma Cloud and needs no Chroma API key. Set `CHROMA_PATH` only if the host
provides a persistent disk; otherwise the database is saved under `chroma_db`
inside the project directory.

## AI service environment variables

The backend uses Cloudflare Workers AI for chat, embeddings, and reranking. Set
these on the Render **backend** service. Do not commit their values:

| Variable | Where to get it |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard account details |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with Workers AI read and edit permissions |

Keep the existing database, authentication, and frontend `API_URL` settings.
The backend does not need `OPENAI_API_KEY`, `HF_TOKEN`, or any Chroma Cloud
credentials for its AI and vector database flows.

## Setup and redeploy

1. Create a Cloudflare account and enable Workers AI. Create an API token with
   Workers AI read and edit permissions.
2. Add `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` to the Render backend.
3. Deploy the updated code and upload the documents again. The new Chroma
   collection is `documents_cf_bge_base_v1` and starts empty.

Cloudflare Workers AI has a daily free allowance; requests can stop when it is
used up. Render's free service has an ephemeral filesystem, so locally stored
Chroma vectors and uploaded source files can disappear when the service
restarts, spins down, or redeploys. For durable Chroma data, the host must
provide a persistent disk and `CHROMA_PATH` must point inside its mount path.
