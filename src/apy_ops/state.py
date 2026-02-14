"""State file backends: local file and Azure Blob Storage."""

import json
import os
import time
import threading
from datetime import datetime, timezone

from azure.storage.blob import BlobServiceClient, BlobLeaseClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential

STATE_VERSION = 1
LEASE_DURATION = 60  # seconds


def empty_state(subscription_id, resource_group, service_name):
    return {
        "version": STATE_VERSION,
        "apim_service": service_name,
        "resource_group": resource_group,
        "subscription_id": subscription_id,
        "last_applied": None,
        "artifacts": {},
    }


class LocalStateBackend:
    """State stored as a local JSON file with .lock file locking."""

    def __init__(self, state_file):
        self.state_file = state_file
        self._lock_file = state_file + ".lock"

    def init(self, subscription_id, resource_group, service_name):
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
        state = empty_state(subscription_id, resource_group, service_name)
        self._write(state)
        return state

    def read(self):
        if not os.path.exists(self.state_file):
            return None
        with open(self.state_file, "r") as f:
            return json.load(f)

    def write(self, state):
        self._write(state)

    def _write(self, state):
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.state_file)

    def lock(self):
        try:
            fd = os.open(self._lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            raise RuntimeError(
                f"State file is locked ({self._lock_file}). "
                "Another process may be running. Use --force-unlock to remove."
            )

    def unlock(self):
        try:
            os.remove(self._lock_file)
        except FileNotFoundError:
            pass

    def force_unlock(self):
        self.unlock()


class AzureBlobStateBackend:
    """State stored in Azure Blob Storage with blob lease locking."""

    def __init__(self, storage_account, container, blob_path,
                 client_id=None, client_secret=None, tenant_id=None):
        if client_id and client_secret and tenant_id:
            credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        else:
            credential = DefaultAzureCredential()
        account_url = f"https://{storage_account}.blob.core.windows.net"
        self._blob_service = BlobServiceClient(account_url, credential=credential)
        self._container_name = container
        self._blob_path = blob_path
        self._container_client = self._blob_service.get_container_client(container)
        self._blob_client = self._container_client.get_blob_client(blob_path)
        self._lease = None
        self._renew_thread = None
        self._stop_renew = threading.Event()

    def init(self, subscription_id, resource_group, service_name):
        # Ensure container exists
        try:
            self._container_client.create_container()
        except Exception:
            pass  # already exists
        state = empty_state(subscription_id, resource_group, service_name)
        self._blob_client.upload_blob(
            json.dumps(state, indent=2), overwrite=True,
        )
        return state

    def read(self):
        try:
            data = self._blob_client.download_blob().readall()
            return json.loads(data)
        except Exception:
            return None

    def write(self, state):
        kwargs = {}
        if self._lease:
            kwargs["lease"] = self._lease
        self._blob_client.upload_blob(
            json.dumps(state, indent=2), overwrite=True, **kwargs,
        )

    def lock(self):
        try:
            lease_client = BlobLeaseClient(self._blob_client)
            lease_client.acquire(lease_duration=LEASE_DURATION)
            self._lease = lease_client
            self._stop_renew.clear()
            self._renew_thread = threading.Thread(
                target=self._renew_loop, daemon=True,
            )
            self._renew_thread.start()
        except Exception as e:
            raise RuntimeError(
                f"Failed to acquire blob lease: {e}. "
                "Another process may hold the lock. Use --force-unlock."
            )

    def _renew_loop(self):
        while not self._stop_renew.wait(timeout=LEASE_DURATION / 2):
            try:
                self._lease.renew()
            except Exception:
                break

    def unlock(self):
        self._stop_renew.set()
        if self._lease:
            try:
                self._lease.release()
            except Exception:
                pass
            self._lease = None

    def force_unlock(self):
        try:
            lease_client = BlobLeaseClient(self._blob_client)
            lease_client.break_lease(lease_break_period=0)
        except Exception:
            pass
        self._lease = None


def get_backend(args):
    """Create the appropriate state backend from CLI args or env vars."""
    backend_type = getattr(args, "backend", None) or os.environ.get("APIM_STATE_BACKEND", "local")

    if backend_type == "azure":
        storage_account = getattr(args, "backend_storage_account", None) or os.environ.get("APIM_STATE_STORAGE_ACCOUNT")
        container = getattr(args, "backend_container", None) or os.environ.get("APIM_STATE_CONTAINER")
        blob_path = getattr(args, "backend_blob", None) or os.environ.get("APIM_STATE_BLOB")
        missing = []
        if not storage_account:
            missing.append("--backend-storage-account or APIM_STATE_STORAGE_ACCOUNT")
        if not container:
            missing.append("--backend-container or APIM_STATE_CONTAINER")
        if not blob_path:
            missing.append("--backend-blob or APIM_STATE_BLOB")
        if missing:
            raise ValueError(
                "Azure state backend requires: " + ", ".join(missing)
            )
        return AzureBlobStateBackend(
            storage_account=storage_account,
            container=container,
            blob_path=blob_path,
            client_id=getattr(args, "client_id", None),
            client_secret=getattr(args, "client_secret", None),
            tenant_id=getattr(args, "tenant_id", None),
        )
    else:
        state_file = getattr(args, "state_file", None) or os.environ.get("APIM_STATE_FILE")
        if not state_file:
            raise ValueError("--state-file or APIM_STATE_FILE is required for local backend")
        return LocalStateBackend(state_file)
