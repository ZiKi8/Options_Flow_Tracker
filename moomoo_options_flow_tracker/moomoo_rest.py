import json
import re
import time
from pathlib import Path

import requests
from requests import RequestException

BASE = "https://webapi.moomoo.com"

class MoomooREST:
    def __init__(
        self,
        token_file="tokens.json",
        max_retries=6,
        default_rate_limit_wait=60,
        request_pause=0.35,
    ):
        self.token_file = Path(token_file)
        if not self.token_file.exists():
            raise RuntimeError("tokens.json not found. Run: python auth_setup.py")

        self.token = json.loads(self.token_file.read_text(encoding="utf-8"))
        self.max_retries = int(max_retries)
        self.default_rate_limit_wait = int(default_rate_limit_wait)
        self.request_pause = float(request_pause)

    def _refresh(self):
        refresh = self.token.get("refresh_token")
        client_id = self.token.get("client_id")
        if not refresh or not client_id:
            raise RuntimeError("Missing refresh token. Re-run auth_setup.py.")

        r = requests.post(
            f"{BASE}/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
            },
            timeout=30,
        )
        r.raise_for_status()

        new = r.json()
        new["refresh_token"] = new.get("refresh_token", refresh)
        new["client_id"] = client_id
        self.token = new
        self.token_file.write_text(json.dumps(new, indent=2), encoding="utf-8")

    @staticmethod
    def _extract_retry_seconds(response, data=None, fallback=60):
        # 1) Standard Retry-After HTTP header
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(1, int(float(header)))
            except ValueError:
                pass

        # 2) Moomoo message such as: "too many requests, retry after 44s"
        text_parts = []
        if isinstance(data, dict):
            text_parts.extend([
                str(data.get("ret_msg", "")),
                str(data.get("error", {}).get("message", "")) if isinstance(data.get("error"), dict) else "",
            ])
        text_parts.append(response.text or "")

        text = " ".join(text_parts)
        m = re.search(r"retry\s+after\s+(\d+)\s*s", text, flags=re.I)
        if m:
            return max(1, int(m.group(1)))

        return fallback

    def get(self, path, params=None):
        last_error = None
        refreshed_once = False

        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.get(
                    BASE + path,
                    params=params,
                    headers={"Authorization": f"Bearer {self.token['access_token']}"},
                    timeout=45,
                )
            except RequestException as e:
                last_error = e
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Network error after {attempt} attempts: {e}") from e
                wait = min(60, 2 ** attempt)
                print(f"[RETRY] network error: {e}. Waiting {wait}s ({attempt}/{self.max_retries})...")
                time.sleep(wait)
                continue

            # Token expired / authorization issue
            if r.status_code in (401, 403) and not refreshed_once:
                print("[AUTH] access token rejected; refreshing token...")
                self._refresh()
                refreshed_once = True
                continue

            # Try to parse JSON, but keep HTTP-level handling usable if parsing fails.
            try:
                data = r.json()
            except ValueError:
                data = None

            # HTTP 429 or Moomoo ret_code -11
            is_rate_limited = (
                r.status_code == 429
                or (
                    isinstance(data, dict)
                    and (
                        data.get("ret_code") == -11
                        or data.get("error", {}).get("code") == "rate_limited"
                        if isinstance(data.get("error"), dict)
                        else False
                    )
                )
            )

            if is_rate_limited:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Moomoo API remained rate-limited after {attempt} attempts: {data or r.text}"
                    )

                wait = self._extract_retry_seconds(
                    r, data, fallback=self.default_rate_limit_wait
                )
                # Add a tiny safety buffer so we do not retry on the exact boundary.
                wait += 2
                print(
                    f"[RATE LIMIT] waiting {wait}s before retry "
                    f"({attempt}/{self.max_retries})..."
                )
                time.sleep(wait)
                continue

            # Temporary server-side error
            if 500 <= r.status_code <= 599:
                if attempt >= self.max_retries:
                    r.raise_for_status()
                wait = min(60, 2 ** attempt)
                print(
                    f"[RETRY] Moomoo server returned HTTP {r.status_code}. "
                    f"Waiting {wait}s ({attempt}/{self.max_retries})..."
                )
                time.sleep(wait)
                continue

            # Other HTTP error
            r.raise_for_status()

            # API-level error
            if isinstance(data, dict) and data.get("ret_code", 0) not in (0, None):
                raise RuntimeError(f"Moomoo API error: {data}")

            # Gentle pacing even when requests succeed.
            if self.request_pause > 0:
                time.sleep(self.request_pause)

            return data

        raise RuntimeError(f"Request failed after retries: {last_error}")

    def option_chain(self, ticker, start, end):
        data = self.get(
            f"/api/v1.0/quote/US.{ticker}/option-chain",
            params={
                "start": start,
                "end": end,
                "filter_standard": "STANDARD",
            },
        )
        return data.get("data", {}).get("option_chain", [])

    def history_kline(self, symbol, start, end, num=20):
        data = self.get(
            f"/api/v1.0/quote/{symbol}/history-kline",
            params={
                "start": start,
                "end": end,
                "ktype": 2,
                "autype": 1,
                "num": num,
                "extended_time": 0,
            },
        )
        return data.get("data", {}).get("kline_list", [])
