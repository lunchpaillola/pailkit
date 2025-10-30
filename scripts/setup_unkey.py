"""
Utility script placeholder to help create initial PailKit keys via Unkey.

Instructions:
1) Create an Unkey workspace and API via the Unkey dashboard.
2) Create initial keys for early users (prefix keys with `pailkit_`).
3) Set the following env vars on the server if you plan to enable runtime
   verification (optional; middleware already enforces key presence/format):
   - UNKEY_API_ID
   - UNKEY_ROOT_KEY

Note: Full Unkey API integration can be added later using the official SDK.
"""

if __name__ == "__main__":
    print(
        "Visit your Unkey dashboard to create an API and keys. "
        "Distribute keys that start with 'pailkit_'."
    )
