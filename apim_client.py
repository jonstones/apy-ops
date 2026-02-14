"""Azure API Management REST API client."""

import time
import requests
from azure.identity import DefaultAzureCredential, ClientSecretCredential

API_VERSION = "2024-05-01"
MAX_RETRIES = 5
INITIAL_BACKOFF = 1  # seconds


class ApimClient:
    """Thin wrapper around Azure APIM REST API with auth and retry."""

    def __init__(self, subscription_id, resource_group, service_name,
                 client_id=None, client_secret=None, tenant_id=None):
        self.base_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ApiManagement/service/{service_name}"
        )
        if client_id and client_secret and tenant_id:
            credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        else:
            credential = DefaultAzureCredential()
        self._credential = credential
        self._token = None
        self._token_expiry = 0

    def _get_token(self):
        now = time.time()
        if self._token and now < self._token_expiry - 60:
            return self._token
        token = self._credential.get_token("https://management.azure.com/.default")
        self._token = token.token
        self._token_expiry = token.expires_on
        return self._token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _request(self, method, path, body=None):
        url = f"{self.base_url}{path}"
        params = {"api-version": API_VERSION}
        backoff = INITIAL_BACKOFF
        for attempt in range(MAX_RETRIES + 1):
            resp = requests.request(
                method, url, headers=self._headers(),
                json=body, params=params, timeout=120,
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", backoff))
                if attempt < MAX_RETRIES:
                    time.sleep(retry_after)
                    backoff *= 2
                    continue
            return resp
        return resp  # return last response if all retries exhausted

    def get(self, path):
        resp = self._request("GET", path)
        resp.raise_for_status()
        return resp.json()

    def list(self, path):
        """GET with pagination support. Returns list of all items."""
        items = []
        url = f"{self.base_url}{path}"
        params = {"api-version": API_VERSION}
        while url:
            backoff = INITIAL_BACKOFF
            resp = None
            for attempt in range(MAX_RETRIES + 1):
                resp = requests.get(
                    url, headers=self._headers(), params=params, timeout=120,
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", backoff))
                    if attempt < MAX_RETRIES:
                        time.sleep(retry_after)
                        backoff *= 2
                        continue
                break
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("nextLink")
            params = {}  # nextLink includes query params
        return items

    def put(self, path, body):
        resp = self._request("PUT", path, body)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    def delete(self, path):
        url = f"{self.base_url}{path}"
        params = {"api-version": API_VERSION}
        resp = requests.delete(
            url, headers=self._headers(), params=params, timeout=120,
        )
        # 404 on delete is fine — already gone
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return None
