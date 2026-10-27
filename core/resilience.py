"""Network resilience and session ledger."""
import email.utils
import json
import os
import random
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional

import requests


class CircuitBreakerTrippedException(Exception):
    """Raised when the circuit breaker is OPEN to protect against account bans."""
    pass

class AdaptiveNetworkManager:
    """Network manager with retry backoff."""

    def __init__(
        self,
        base_delay: float = 1.5,
        max_delay: float = 60.0,
        max_retries: int = 5,
        circuit_threshold: int = 4,
        circuit_cooldown: float = 120.0
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.circuit_threshold = circuit_threshold
        self.circuit_cooldown = circuit_cooldown

        self.consecutive_rate_limits = 0
        self.circuit_state = "CLOSED"  # State can be CLOSED, OPEN, or HALF-OPEN.
        self.circuit_tripped_time = 0.0
        self.latency_ema = 0.4  # Exponential moving average of request latency in seconds.

    def _calculate_backoff_sleep(self, attempt: int) -> float:
        """Full Jitter formula: uniform(0.5 * capped, capped)."""
        exponential = self.base_delay * (2 ** attempt)
        capped = min(self.max_delay, exponential)
        return random.uniform(0.5 * capped, capped)

    def _parse_retry_after(self, response: requests.Response) -> Optional[float]:
        """Parses standard HTTP Retry-After header if present."""
        val = response.headers.get("Retry-After")
        if not val:
            return None

        # Integer seconds format.
        if val.isdigit():
            return max(1.0, float(val))

        # RFC 2822 date format.
        try:
            target_dt = email.utils.parsedate_to_datetime(val)
            now_dt = email.utils.datetime.datetime.now(email.utils.timezone.utc)
            delta = (target_dt - now_dt).total_seconds()
            return max(1.0, delta)
        except Exception:
            return None

    def record_success(self, duration: float):
        """Update metrics on successful network response."""
        self.consecutive_rate_limits = 0
        if self.circuit_state == "HALF-OPEN":
            self.circuit_state = "CLOSED"
        self.latency_ema = 0.2 * duration + 0.8 * self.latency_ema

    def record_failure(self, is_rate_limit: bool):
        """Update circuit breaker on failure."""
        if is_rate_limit:
            self.consecutive_rate_limits += 1
            if self.consecutive_rate_limits >= self.circuit_threshold:
                self.circuit_state = "OPEN"
                self.circuit_tripped_time = time.time()

    def check_circuit(self):
        """Verify circuit breaker state before executing."""
        if self.circuit_state == "OPEN":
            elapsed = time.time() - self.circuit_tripped_time
            if elapsed > self.circuit_cooldown:
                self.circuit_state = "HALF-OPEN"
            else:
                remaining = self.circuit_cooldown - elapsed
                raise CircuitBreakerTrippedException(
                    f"[CIRCUIT_OPEN] Rate limit protection active. Cooling down for {remaining:.1f}s."
                )

    def pace_request(self):
        """Dynamic inter-request delay influenced by rolling server latency."""
        jitter = random.uniform(0.85, 1.25)
        delay = (self.base_delay + (self.latency_ema * 0.4)) * jitter
        time.sleep(delay)

    def execute(self, request_fn: Callable[[], requests.Response]) -> requests.Response:
        """Executes a request callable with resilience wrapping."""
        self.check_circuit()

        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                self.pace_request()
                resp = request_fn()
                dur = time.time() - t0

                if resp.status_code in (429, 403, 503):
                    is_429 = resp.status_code == 429
                    self.record_failure(is_rate_limit=is_429)

                    retry_after = self._parse_retry_after(resp)
                    sleep_time = retry_after if retry_after else self._calculate_backoff_sleep(attempt)

                    if attempt < self.max_retries:
                        time.sleep(sleep_time)
                        continue
                    return resp

                if resp.status_code == 200:
                    self.record_success(dur)
                    return resp

                return resp

            except (requests.ConnectionError, requests.Timeout, requests.RequestException):
                self.record_failure(is_rate_limit=False)
                if attempt < self.max_retries:
                    sleep_time = self._calculate_backoff_sleep(attempt)
                    time.sleep(sleep_time)
                else:
                    raise

        raise RuntimeError("[NETWORK_EXHAUSTED] Maximum retries exceeded across backoff attempts.")


class SessionCheckpointLedger:
    """Ledger tracking download progress."""

    def __init__(self, checkpoint_path: str = ".download_checkpoint.json"):
        self.path = os.path.abspath(checkpoint_path)
        self.state: Dict[str, Any] = {
            "version": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
            "pagination_cursor": None,
            "pending_urls": [],
            "completed_ids": [],
            "failed_records": {},  # {url: {"error": str, "attempts": int, "retry_at": float}}
        }
        self.load()

    def load(self):
        """Load state from disk if present."""
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception:
                pass

    def save(self):
        """Atomically persist state to disk via write-then-rename."""
        self.state["updated_at"] = time.time()
        dir_name = os.path.dirname(self.path) or "."
        os.makedirs(dir_name, exist_ok=True)

        fd, tmp_file = tempfile.mkstemp(dir=dir_name, prefix=".chk_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
            os.replace(tmp_file, self.path)
        except Exception:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    def initialize_batch(self, urls: List[str]):
        """Register a new list of URLs to process."""
        completed_set = set(self.state.get("completed_ids", []))
        current_pending = set(self.state.get("pending_urls", []))
        for u in urls:
            u_clean = u.strip()
            if u_clean and u_clean not in completed_set and u_clean not in current_pending:
                self.state["pending_urls"].append(u_clean)
        self.save()

    def mark_completed(self, item_id: str, url: str):
        """Mark an item as successfully downloaded."""
        if item_id and item_id not in self.state["completed_ids"]:
            self.state["completed_ids"].append(item_id)
        if url in self.state["pending_urls"]:
            self.state["pending_urls"].remove(url)
        self.state["failed_records"].pop(url, None)
        self.save()

    def mark_failed(self, url: str, error_msg: str, retry_delay: float = 45.0):
        """Record an item failure with backoff retry timestamp."""
        record = self.state["failed_records"].get(url, {"attempts": 0})
        record["attempts"] += 1
        record["error"] = error_msg
        record["retry_at"] = time.time() + retry_delay
        self.state["failed_records"][url] = record
        self.save()

    def update_pagination_cursor(self, cursor: Optional[str]):
        """Persist API feed pagination cursor (e.g. Instagram max_id)."""
        self.state["pagination_cursor"] = cursor
        self.save()

    def get_pending_queue(self) -> List[str]:
        """Return URLs eligible for processing right now."""
        now = time.time()
        queue = list(self.state.get("pending_urls", []))

        # Include retriable failures whose delay has elapsed.
        for url, record in self.state.get("failed_records", {}).items():
            if now >= record.get("retry_at", 0) and record.get("attempts", 0) < 4:
                if url not in queue:
                    queue.append(url)
        return queue


class ProxyNode:
    """Represents a proxy endpoint with health and latency metrics."""
    def __init__(self, raw_url: str):
        self.url = raw_url.strip()
        self.is_healthy = True
        self.latency = 999.0
        self.failures = 0
        self.quarantine_until = 0.0

    def to_requests_dict(self) -> Dict[str, str]:
        return {"http": self.url, "https": self.url}

class ResilientProxyPool:
    """Proxy pool manager with health checks."""

    def __init__(self, proxy_list: List[str], probe_target: str = "https://www.instagram.com/robots.txt"):
        self.nodes = [ProxyNode(p) for p in proxy_list if p.strip()]
        self.probe_target = probe_target
        self.index = 0

    def probe_node(self, node: ProxyNode) -> bool:
        """Probe proxy connectivity and record latency."""
        try:
            t0 = time.time()
            resp = requests.get(
                self.probe_target,
                proxies=node.to_requests_dict(),
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                node.latency = time.time() - t0
                node.is_healthy = True
                node.failures = 0
                return True
        except Exception:
            pass

        node.failures += 1
        node.is_healthy = False
        node.quarantine_until = time.time() + (45.0 * (2 ** min(node.failures, 4)))
        return False

    def get_proxy(self) -> Optional[ProxyNode]:
        """Get next available healthy proxy via round-robin."""
        now = time.time()
        healthy = []
        for n in self.nodes:
            if not n.is_healthy and now >= n.quarantine_until:
                self.probe_node(n)
            if n.is_healthy:
                healthy.append(n)

        if not healthy:
            return None

        self.index = (self.index + 1) % len(healthy)
        return healthy[self.index]

    def report_failure(self, node: ProxyNode):
        """Immediately quarantine failing proxy."""
        node.failures += 1
        node.is_healthy = False
        node.quarantine_until = time.time() + (45.0 * (2 ** min(node.failures, 4)))
