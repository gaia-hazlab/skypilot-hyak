# /// script
# requires-python = ">=3.12"
# [tool.pixi.workspace]
# channels = ["conda-forge"]
# platforms = ["osx-arm64", "linux-64"]
# [tool.pixi.dependencies]
# boto3 = "*"
# rich = "*"
# ///
"""Kopah storage usage per bucket and first-level prefix, vs. the account quota.

    pixi run --script scripts/kopah-usage.py              # buckets + prefixes (~1 min)
    pixi run --script scripts/kopah-usage.py -- --quick   # metered totals only (~1 s)

Script options go after `--`, otherwise pixi parses them as its own.

Bucket rows and the total are Kopah's own metered numbers (Ceph RGW `GET /?usage`,
the same bytes the quota is enforced on, rounded up to 4 KiB per object). Prefix
rows come from listing every object, so they don't include incomplete multipart
uploads, which are shown in their own row.

Credentials: the AWS profile `kopah` (see docs/kopah.md), else AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY (+ optional S3_ENDPOINT_URL).
"""

import argparse
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import boto3
import botocore.auth
import botocore.awsrequest
import botocore.config
from rich.console import Console
from rich.table import Table

DEFAULT_ENDPOINT = "https://s3.kopah.uw.edu"
console = Console(stderr=True)


def make_session(profile: str) -> tuple[boto3.Session, str]:
    """Return a boto3 session and the S3 endpoint URL."""
    if profile in boto3.Session().available_profiles:
        session = boto3.Session(profile_name=profile)
        endpoint = session._session.get_scoped_config().get("endpoint_url", DEFAULT_ENDPOINT)
        return session, endpoint
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return boto3.Session(), os.environ.get("S3_ENDPOINT_URL", DEFAULT_ENDPOINT)
    sys.exit(f"No credentials: no AWS profile {profile!r} and no AWS_ACCESS_KEY_ID")


class Kopah:
    def __init__(self, session: boto3.Session, endpoint: str):
        self.endpoint = endpoint.rstrip("/")
        self.s3 = session.client(
            "s3",
            endpoint_url=self.endpoint,
            config=botocore.config.Config(
                max_pool_connections=32,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self.creds = session.get_credentials().get_frozen_credentials()
        self.region = self.s3.meta.region_name or "us-east-1"

    def _rgw(self, method: str, path: str):
        """Signed request for RGW extensions that boto3 has no API call for."""
        req = botocore.awsrequest.AWSRequest(method=method, url=self.endpoint + path)
        botocore.auth.S3SigV4Auth(self.creds, "s3", self.region).add_auth(req)
        r = urllib.request.Request(req.url, method=method, headers=dict(req.headers))
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.headers, resp.read()

    def usage(self) -> dict:
        """Quota + metered bytes per bucket (RGW `GET /?usage`)."""
        _, body = self._rgw("GET", "/?usage")
        root = ET.fromstring(body)
        for el in root.iter():  # drop the XML namespace, if any
            el.tag = el.tag.rpartition("}")[2]
        s = root.find("Summary")
        return {
            "quota_bytes": int(s.findtext("QuotaMaxBytes")),
            "quota_objects": int(s.findtext("QuotaMaxObjCount")),
            "total_bytes": int(s.findtext("TotalBytesRounded")),
            "total_objects": int(s.findtext("TotalEntries")),
            "buckets": {
                e.findtext("Bucket"): int(e.findtext("Bytes_Rounded"))
                for e in root.iterfind("CapacityUsed/User/Buckets/Entry")
            },
        }

    def object_count(self, bucket: str) -> int:
        headers, _ = self._rgw("HEAD", f"/{bucket}?read-stats=true")
        return int(headers.get("X-RGW-Object-Count", 0))

    def prefixes(self, bucket: str) -> dict[str, tuple[int, int]]:
        """{first-level prefix: (bytes, objects)}; top-level files go under '(files)'."""
        out: dict[str, tuple[int, int]] = {}
        tops = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Delimiter="/"
        ):
            tops += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
            files = page.get("Contents", [])
            if files:
                b, n = out.get("(files)", (0, 0))
                out["(files)"] = (b + sum(o["Size"] for o in files), n + len(files))

        def walk(prefix):
            size = count = 0
            for page in self.s3.get_paginator("list_objects_v2").paginate(
                Bucket=bucket, Prefix=prefix
            ):
                for o in page.get("Contents", []):
                    size += o["Size"]
                    count += 1
            return prefix, (size, count)

        with ThreadPoolExecutor(16) as pool:
            out.update(pool.map(walk, tops))
        return out

    def incomplete_uploads(self, bucket: str) -> tuple[int, int]:
        """(bytes, uploads) held by multipart uploads that were never completed."""
        size = uploads = 0
        for page in self.s3.get_paginator("list_multipart_uploads").paginate(Bucket=bucket):
            for u in page.get("Uploads", []):
                uploads += 1
                for p in self.s3.get_paginator("list_parts").paginate(
                    Bucket=bucket, Key=u["Key"], UploadId=u["UploadId"]
                ):
                    size += sum(part["Size"] for part in p.get("Parts", []))
        return size, uploads


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="kopah", help="AWS profile (default: kopah)")
    ap.add_argument("--quick", action="store_true", help="skip per-prefix listing")
    ap.add_argument(
        "--min-percent",
        type=float,
        default=0.1,
        help="fold prefixes smaller than this %% of quota into one row (default 0.1)",
    )
    args = ap.parse_args()

    k = Kopah(*make_session(args.profile))
    with console.status("Fetching usage..."):
        u = k.usage()
        with ThreadPoolExecutor(8) as pool:
            counts = dict(zip(u["buckets"], pool.map(k.object_count, u["buckets"])))
    quota = u["quota_bytes"]
    pct = lambda b: f"{100 * b / quota:.1f}%"

    table = Table(title=f"Kopah usage ({k.endpoint})", title_justify="left")
    table.add_column("Bucket / prefix")
    table.add_column("Size", justify="right")
    table.add_column("Objects", justify="right")
    table.add_column("% quota", justify="right")

    for bucket, nbytes in sorted(u["buckets"].items(), key=lambda kv: -kv[1]):
        table.add_row(f"[bold]{bucket}[/]", human(nbytes), f"{counts[bucket]:,}", pct(nbytes),
                      style="bold")
        if args.quick or counts[bucket] == 0:
            continue
        with console.status(f"Listing {bucket} ({counts[bucket]:,} objects)..."):
            prefixes = k.prefixes(bucket)
            mpu_bytes, mpu_n = k.incomplete_uploads(bucket)
        small_b = small_n = small_k = 0
        for p, (b, n) in sorted(prefixes.items(), key=lambda kv: -kv[1][0]):
            if 100 * b / quota < args.min_percent:
                small_b, small_n, small_k = small_b + b, small_n + n, small_k + 1
                continue
            table.add_row(f"  {p}", human(b), f"{n:,}", pct(b))
        if small_k:
            table.add_row(f"  [dim]({small_k} smaller prefixes)[/]", human(small_b),
                          f"{small_n:,}", pct(small_b), style="dim")
        if mpu_n:
            table.add_row(f"  [yellow]incomplete multipart uploads ({mpu_n})[/]",
                          human(mpu_bytes), "", pct(mpu_bytes), style="yellow")

    remaining = quota - u["total_bytes"]
    color = "red" if remaining < 0.1 * quota else "yellow" if remaining < 0.25 * quota else "green"
    table.add_section()
    table.add_row("[bold]Total (metered)[/]", human(u["total_bytes"]),
                  f"{u['total_objects']:,}", pct(u["total_bytes"]), style="bold")
    table.add_row("Quota", human(quota), f"{u['quota_objects']:,}", "100.0%")
    table.add_row(f"[{color}]Remaining[/]", f"[{color}]{human(remaining)}[/]",
                  f"{u['quota_objects'] - u['total_objects']:,}", f"[{color}]{pct(remaining)}[/]")
    Console().print(table)


if __name__ == "__main__":
    main()
