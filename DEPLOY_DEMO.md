# Deploying the client demo (Streamlit Community Cloud)

This deploys a **separate, public demo instance** seeded with synthetic
sample data — not the real Favor Church deployment, which stays local-only
(`streamlit run app/main.py`) and is never exposed publicly.

The demo's data comes from `app/core/demo_seed.py`, gated behind the
`DEMO_MODE` secret set below. It reseeds itself from scratch on every cold
start (Community Cloud's filesystem isn't persistent across redeploys/
sleeps), so there's nothing to back up and no way for it to accumulate
real data over time.

## One-time setup

1. Push this branch (or merge it into whichever branch you want the demo
   to track) to GitHub — Community Cloud deploys straight from a branch.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub. If this is your first deploy, authorize Streamlit's GitHub App
   for the `wilu-git/bir2307-app` repo (Community Cloud supports private
   repos).
3. Click **New app**.
   - **Repository:** `wilu-git/bir2307-app`
   - **Branch:** `feature/demo-deployment` (or wherever you merge this)
   - **Main file path:** `bir2307-app/app/main.py`
   - **App URL:** pick something like `bir2307-demo` → gives you
     `https://bir2307-demo.streamlit.app`
4. Before clicking Deploy, open **Advanced settings → Secrets** and paste:

   ```toml
   APP_PASSWORD = "pick-a-demo-password"
   DEMO_MODE = "true"
   ```

   (Template lives at `.streamlit/secrets.toml.example` — same idea, real
   values go in the dashboard, never in a committed file.) Use a
   **different** password than the real deployment's `APP_PASSWORD`.
5. Click **Deploy**. First build takes a few minutes (installing
   `requirements.txt`).

## Verify it worked

- Open the app URL, sign in with the demo password.
- **Certificates** page should show ~11 certificates with a mix of
  statuses (draft/generated/forwarded/completed_signed).
- **Records** page's payor should read "Sample Ministries Foundation Inc.
  (DEMO DATA)" — if it still shows "PLACEHOLDER TIN", `DEMO_MODE` wasn't
  picked up (check the secret is exactly `DEMO_MODE = "true"`, and redeploy).
- **Logs** page should show a realistic mix of TIN_FORMAT,
  COMPUTATION_MISMATCH, ATC_RATE_UNKNOWN, DUPLICATE_REFERENCE, and
  ROW_VALIDATION entries — this is the most convincing part of the demo,
  since it's the app's real validation pipeline reacting to real (synthetic)
  bad data, not staged content.

## Giving clients access

Share the app URL + the demo password. Nothing else to configure — the
existing password gate (`app/core/auth.py`) is reused as-is.

## Updating the demo

Push to the branch Community Cloud is tracking; it redeploys automatically
and reseeds fresh demo data on the next cold start. To change what the
demo shows, edit `_DEMO_ROWS` in `app/core/demo_seed.py`.

## Redeploying after inactivity

Community Cloud sleeps apps after a period of no traffic. The first visitor
after a sleep triggers a cold start (~30s) and a fresh reseed — expected
behavior, not a bug. If you're about to demo it live, open the link
yourself a minute beforehand to warm it up.

## Turning it off

Delete the app from the Community Cloud dashboard (or just stop sharing
the link/password) when you no longer need a live demo running.
