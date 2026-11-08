"""Start Tiger's local OAuth2 authorization flow for a read-only Argus test."""
from __future__ import annotations


def authorize_with_device_code(sessions, emit=print) -> None:
    """Use a browser-independent OAuth device flow suitable for a Linux guest."""
    def show_authorization(device) -> None:
        url = getattr(device, "verification_uri_complete", None) or getattr(device, "verification_uri", None)
        user_code = getattr(device, "user_code", None)
        if not url or not user_code:
            raise RuntimeError("Tiger returned an incomplete device authorization challenge")
        emit(f"Open this Tiger authorization page on Windows: {url}")
        emit(f"Enter this one-time user code: {user_code}")

    sessions.login_with_device_code_if_needed(show_authorization)


def main() -> int:
    try:
        from tigeropen.auth.oauth2 import OAuth2SessionManager
    except ImportError as exc:
        print("Install tigeropen==3.8.0 in this Python environment first.")
        return 1

    sessions = OAuth2SessionManager()
    authorize_with_device_code(sessions)
    print("Tiger OAuth authorization completed. No RSA private key was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
