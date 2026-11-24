# Bucket access logging on Kopah

S3 bucket logging is the tenant-facing option. Ceph RGW supports the standard `PutBucketLogging` API, which writes S3-style access log records to a bucket you choose. It's per-bucket and opt-in, so it isn't on by default. It is a recent feature:

- **Squid 19.2.2** (2025-04-10): introduced as a Technology Preview.
- **Tentacle 20.2.0** (2025-11-18): the [Ceph docs](https://docs.ceph.com/en/latest/radosgw/bucket_logging/) mark it "Added in version Tentacle".

Kopah needs to be on 19.2.2+ (ideally Tentacle) for this to work. Kopah's backend isn't documented, but its response headers point to Ceph RGW: the `x-amz-request-id` format is `tx<counter>-<hex unix time>-<instance>-<zone>`.

> **Status (2026-10-13): not supported on Kopah.** UW IT confirmed: "The Ceph version Kopah is running does not support this feature. We prioritize stability for our researchers and are currently running a stable, well-tested version. We don't have plans for a Ceph upgrade in the short term, but we will keep this feature request on our list for future consideration." They didn't say which release Kopah runs, only that it's older than 19.2.2. Until that changes, use the [logging redirect endpoint](#alternative-a-logging-redirect-endpoint) below. The setup steps are kept for when Kopah upgrades.

Goal: capture access logs for the Cloud-Optimized GeoTIFFs under `s3://gaia/grimp/cogs/`.

## Things to know

- **Logs go to a separate bucket.** The Ceph docs say: "The log bucket cannot be the same as the bucket being logged." We use `gaia-logs`.
- **Logging is bucket-wide.** Standard S3 logging can't be scoped to a prefix, so every request to `gaia` is logged. Filter for `grimp/cogs/` afterwards. Ceph supports prefix/suffix key filters only in its non-AWS "Journal" logging mode, which `aws s3api` may reject during its own parameter checking.
- **The log bucket needs a policy** that lets the `logging.s3.amazonaws.com` principal `s3:PutObject` under the log prefix, scoped to the source bucket: [gaia-logs-policy.json](gaia-logs-policy.json). Ceph also recommends an `aws:SourceAccount` condition (your RGW user/tenant ID).
- **Logs are batched.** Ceph rolls a log object every few minutes (`ObjectRollTime` defaults to 5 minutes), so nothing shows up right away.
- **`grimp/cogs/` isn't public.** Under [gaia-policy.json](gaia-policy.json), only `public/*`, `bkerns/public/*` and `scratch/public/*` are readable anonymously. Anonymous requests for COGs get a 403, but they are still logged.

## Checking the Ceph version

Tenants can't query it directly. The endpoint sits behind Apache (`Server: Apache/2.4.52 (Ubuntu)`), and RGW's admin API needs admin credentials. The practical check is to probe the feature itself. If that fails, ask Hyak support which Ceph release Kopah runs. (As of 2026-10-13, UW IT says only that the release predates bucket logging, i.e. older than 19.2.2.)

`get-bucket-logging` is **not** a reliable probe. Older RGW releases answer it with an empty `<BucketLoggingStatus/>` even though they can't log, and the aws CLI prints nothing for that response. On Kopah (2026-10) it returns exactly that empty response, which is inconclusive. The real test is `put-bucket-logging` (step 2): a `NotImplemented` or `InvalidArgument` error means it's unsupported.

## Setup

```bash
EP=https://s3.kopah.uw.edu

# 0. current state (empty output = not enabled; does NOT prove support, see above)
aws s3api get-bucket-logging --endpoint-url $EP --bucket gaia

# 1. separate log bucket + policy allowing log delivery
aws s3api create-bucket --endpoint-url $EP --bucket gaia-logs
aws s3api put-bucket-policy --endpoint-url $EP --bucket gaia-logs \
  --policy file://docs/gaia-logs-policy.json

# 2. enable logging on gaia -> gaia-logs
aws s3api put-bucket-logging --endpoint-url $EP --bucket gaia \
  --bucket-logging-status '{"LoggingEnabled":{"TargetBucket":"gaia-logs","TargetPrefix":"gaia/"}}'
aws s3api get-bucket-logging --endpoint-url $EP --bucket gaia

# 3. generate traffic, wait ~5+ min, then look
curl -sI $EP/gaia/public/<some-object>
aws s3 ls --endpoint-url $EP s3://gaia-logs/gaia/
```

## Reading the logs

```bash
# pull logs locally and keep only COG requests
aws s3 cp --endpoint-url $EP --recursive s3://gaia-logs/gaia/ ./gaia-logs/
grep -h ' grimp/cogs/' ./gaia-logs/* | less
```

Consider a lifecycle rule on `gaia-logs` (see [kopah.md](kopah.md#lifecycle-policies)) so old logs expire.

## Disable

```bash
aws s3api put-bucket-logging --endpoint-url $EP --bucket gaia --bucket-logging-status '{}'
```

## Alternative: a logging redirect endpoint

Kopah can't do bucket logging (`put-bucket-logging` returns `MethodNotAllowed`, and UW IT has no short-term upgrade planned), so put a small service in front of the bucket. It logs each request and then redirects the client to a short-lived presigned Kopah URL:

```
client --GET /cogs/<key>--> redirect service --(log ts, key, ip, ua)--> SQLite/Postgres
       <--302 Location: presigned https://s3.kopah.uw.edu/gaia/grimp/cogs/<key>?X-Amz-...--
client --GET (Range) ----> Kopah
```

Data still flows directly from Kopah, so Kopah's free egress is kept and the service only handles tiny requests. The objects stay private: `grimp/cogs/` is not in the public prefixes of [gaia-policy.json](gaia-policy.json).

### Minimal FastAPI sketch

```python
import sqlite3, time
import boto3
from botocore.config import Config
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

s3 = boto3.client(
    "s3",
    endpoint_url="https://s3.kopah.uw.edu",
    # Kopah has no virtual-host DNS (gaia.s3.kopah.uw.edu doesn't resolve)
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
db = sqlite3.connect("access.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS hits (ts REAL, key TEXT, ip TEXT, method TEXT, range TEXT, ua TEXT)")
app = FastAPI()

@app.api_route("/cogs/{key:path}", methods=["GET", "HEAD"])
def cog(key: str, request: Request):
    # behind a proxy, the real client is the first X-Forwarded-For entry
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    db.execute("INSERT INTO hits VALUES (?,?,?,?,?,?)",
               (time.time(), key, ip, request.method,
                request.headers.get("range"), request.headers.get("user-agent")))
    db.commit()
    op = "head_object" if request.method == "HEAD" else "get_object"
    url = s3.generate_presigned_url(op, Params={"Bucket": "gaia", "Key": f"grimp/cogs/{key}"},
                                    ExpiresIn=3600)
    return RedirectResponse(url, status_code=302)
```

A Cloudflare Worker can do the same: sign with `aws4fetch` and log to D1 or Analytics Engine.

### Caveats for COGs specifically

- **"Downloads" are fuzzy for COGs.** Clients such as GDAL/rasterio, TiTiler and geotiff.js read with many HTTP range requests rather than one download. GDAL caches the redirect target and reuses the presigned URL until it nears expiry, so you'll mostly log one hit per file *open*, not per tile read. Count distinct (ip, key, hour) rather than raw rows.
- **URLs change.** Users and any STAC catalog must use the service URL (`https://<service>/cogs/<key>`), not `s3://gaia/...` or the Kopah URL. Anyone with Kopah credentials, and anyone holding a not-yet-expired presigned URL, bypasses the log.
- **The service becomes a dependency.** If it's down, the data is unreachable. It needs hosting, TLS and its own Kopah key (use a read-only key if Kopah allows scoped users).
- **Browser clients need CORS** on the service *and* on the `gaia` bucket (`put-bucket-cors`), because the 302 crosses origins. Expose `Content-Range`, `Content-Length` and `ETag`, and allow the `Range` header.
- **Long reads past expiry.** GDAL re-requests the original service URL when the presigned URL expires, so that works. Other clients may fail, so keep `ExpiresIn` comfortably long (around 1h).
- **Privacy.** Storing IPs is personal data. Consider truncating or hashing IPs and setting a retention period.
- **Don't proxy the bytes.** Streaming data through the service instead of redirecting loses free egress and makes the service a bandwidth bottleneck.
