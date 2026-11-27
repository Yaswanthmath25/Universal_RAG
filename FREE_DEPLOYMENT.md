# Low-cost deployment setup

The backend can use Cloudflare Workers AI for chat, embeddings, and reranking,
and Chroma Cloud for persistent vectors. Local development continues to use
the on-disk Chroma database when Chroma Cloud credentials are not set.

## Required backend environment variables

Set these on the Render **backend** service. Do not commit their values:

| Variable | Where to get it |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard account details |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with Workers AI read and edit permissions |
| `CHROMA_API_KEY` | Chroma Cloud database credentials |
| `CHROMA_TENANT` | Chroma Cloud database credentials |
| `CHROMA_DATABASE` | Chroma Cloud database credentials |

Keep the existing database, authentication, and frontend `API_URL` settings.
The backend no longer needs `OPENAI_API_KEY` or `HF_TOKEN` for its AI flows.

## Setup and redeploy

1. Create a Cloudflare account and enable Workers AI. Create an API token with
   Workers AI read and edit permissions.
2. Create a Chroma Cloud database and copy its API key, tenant, and database
   name.
3. Add all five values above to the Render backend service's environment.
4. Deploy the updated code. The backend creates a new
   `documents_cf_bge_base_v1` collection in Chroma Cloud.
5. Remove stale document records from the admin portal if they remain from the
   previous deployment, then upload the documents again. Existing local vectors
   are not copied to the new cloud collection.

Cloudflare Workers AI has a daily free allowance; requests can stop when it is
used up. Chroma Cloud currently includes $5 in starter credits and then charges
based on usage. These services need credentials, but they do not use the old
OpenAI API key.

Render's free service has an ephemeral filesystem. Chroma vectors are stored in
Chroma Cloud, but original uploaded files under the local `uploads` directory
can disappear when Render restarts or redeploys.
