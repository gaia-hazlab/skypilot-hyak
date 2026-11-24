# Kopah

UW Hyak now provides a managed object store called Kopah

https://hyak.uw.edu/docs/storage/kopah

Kopah was announced as a preview in [August 2024](https://hyak.uw.edu/blog/2024-august-maintenance), with test users invited ahead of a September rollout. The [overview](https://hyak.uw.edu/docs/systems/kopah/overview) says the service started in Fall 2024. Globus support followed in Spring 2025.

https://github.com/maouw/kopah-uw-s3api-test

You must apply for a trial account or pay-as-you go storage. Here's a current price comparison for blob storage options (as of 05/2026):

| Storage | Cost/TB/mo | Egress | Commitment |
|---|---|---|---|
| **[UW Kopah](https://hyak.uw.edu/docs/storage/kopah)** | $5.04 | Free | Month-to-month |
| **[Backblaze B2](https://www.backblaze.com/cloud-storage)** | $6.95 ([as of 10/2026](https://www.backblaze.com/cloud-storage/pricing)), first 10 GB free | Free up to 3x storage, then $0.01/GB; unlimited via CDN partners (Cloudflare, Fastly, etc.) | None (1–5 yr discounts) |
| **[Cloudflare R2](https://www.cloudflare.com/developer-platform/r2/)** | $15.00 ([as of 10/2026](https://developers.cloudflare.com/r2/pricing/)), first 10 GB free; $10.00 Infrequent Access | Free | None |
| **[Hugging Face Storage Buckets](https://huggingface.co/docs/hub/en/storage-buckets)** | $18.00 private / $12.00 public ([as of 10/2026](https://huggingface.co/storage)) | Free up to 8:1 egress:storage | None |
| **[Azure Blob Storage](https://azure.microsoft.com/en-us/products/storage/blobs)** | $18.00 | $0.087/GB | None |
| **[Google Cloud Storage](https://cloud.google.com/storage)** | $23.00 | $0.08/GB | None |
| **[AWS S3 Standard](https://aws.amazon.com/s3/)** | $23.55 | $0.09/GB | None |


## Setup

You can use a variety of CLI tools to interact with Kopah. Pre-installed on nodes is s3cmd, s5cmd, and rclone.

### S5cmd

Note: this is only pre-installed on *login* nodes by default https://hyak.uw.edu/docs/storage/cli#s5cmd

We'll use s5cmd (you get these keys from UW IT when you setup a Kopah account):

```bash
export AWS_ACCESS_KEY_ID='<Kopah ACCESS KEY>'     # replace with Kopah access key
export AWS_SECRET_ACCESS_KEY='<Kopah SECRET KEY>' # replace with Kopah secret key
export S3_ENDPOINT_URL='https://s3.kopah.uw.edu'
```


### Create a project bucket (global namespace)

```bash
s5cmd mb s3://gaia
```

```
s5cmd ls s3://gaia
```

#### test upload / download

```
s5cmd cp README.txt s3://gaia/README.txt

s5cmd cp README.txt s3://gaia/scottyh/README.txt

s5cmd cp "s3://gaia/*" $SCRATCH/kopah-test
```

### Setup rclone

create an `~/.config/rclone/rclone.conf` with the following content (replace with your keys):

```
[kopah]
type = s3
provider = Ceph
access_key_id = <Kopah ACCESS KEY>
secret_access_key = <Kopah SECRET KEY>
endpoint = s3.kopah.uw.edu
acl = private
```

test with `rclone ls kopah:gaia`

## Tracking usage (1 TiB quota)

Our account has a hard quota of 1 TiB across all buckets.
[`scripts/kopah-usage.py`](../scripts/kopah-usage.py) prints usage per bucket and first-level
prefix, plus quota remaining, using Kopah's own metered numbers. It only needs `pixi`:

```bash
pixi run --script scripts/kopah-usage.py              # buckets + prefixes (~1 min)
pixi run --script scripts/kopah-usage.py -- --quick   # totals only (~1 s)
```

Incomplete multipart uploads count against the quota but don't show up in `rclone size` or
`aws s3 ls`; the script lists them in their own row.

## Copying data in from AWS S3 or Azure Blob (rclone)

`rclone copy` streams straight from the other cloud into Kopah. The bytes pass through the machine running rclone, but nothing is written to its disk, so you don't need scratch space. Both procedures below were tested in November 2026, rclone v1.73.2 (the version on klone), and reached about 77 MiB/s from a klone compute node.

### 1. Run it on a klone compute node inside tmux

Don't run a multi-hour copy over home wifi or on a login node.

```bash
ssh <netid>@klone-login01.hyak.uw.edu     # note which login node; tmux sessions live only on that one
hyakalloc                                  # check free capacity for your account
tmux new -s backup
salloc -A <account> -p cpu-g2 -c 4 --mem=16G --time=8:00:00    # or -p ckpt if cpu-g2 is full
```

Detach with `Ctrl-b d`. To come back, ssh to the **same** login node and run `tmux attach -t backup`. Environment variables you set (credentials below) exist only in the shell where you set them. Set them again after a new `salloc` or in a new tmux window.

### 2a. Source: AWS S3

Add an `aws` remote next to `kopah` in `~/.config/rclone/rclone.conf`:

```ini
[aws]
type = s3
provider = AWS
region = us-west-2
```

If your AWS profile assumes a role **with MFA**, rclone can't prompt for the code (`assume role with MFA enabled, but AssumeRoleTokenProvider session option not set`). Let the AWS CLI prompt, then hand the temporary credentials **only to the `aws` remote** by renaming the variables. Plain `AWS_*` variables would also override the `kopah` remote's credentials.

```bash
unset AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
eval "$(aws configure export-credentials --profile <aws-profile> --format env | sed 's/export AWS_/export RCLONE_CONFIG_AWS_/')"
export RCLONE_CONFIG_AWS_ENV_AUTH=false
echo $RCLONE_CONFIG_AWS_CREDENTIAL_EXPIRATION   # re-run the eval line after this time

rclone lsd aws:<bucket>
SRC=aws:<bucket>/<prefix>
```

If the copy dies with `ExpiredToken`, re-run the `eval` line and then the same `rclone copy`; files already copied are skipped. `rclone copy` copies only current object versions, so check `aws s3api get-bucket-versioning` before deleting a source bucket.

### 2b. Source: Azure Blob

Don't put the storage account key on klone. On your laptop, generate a short-lived, **read+list-only**, HTTPS-only SAS limited to one container:

```bash
# laptop (macOS date syntax); needs an az login that can list the account keys
EXP=$(date -u -v+3d +%Y-%m-%dT%H:%MZ)
KEY=$(az storage account keys list -g <resource-group> -n <account> --query "[0].value" -o tsv)
SAS=$(az storage container generate-sas --account-name <account> --account-key "$KEY" \
      -n <container> --permissions rl --expiry $EXP --https-only -o tsv)
unset KEY
[ -n "$SAS" ] && echo "https://<account>.blob.core.windows.net/<container>?$SAS"
```

On klone, paste it into an environment variable. rclone's on-the-fly `:azureblob:` remote reads it, so nothing goes into `rclone.conf`:

```bash
read -rs RCLONE_AZUREBLOB_SAS_URL      # paste the URL, press Enter. -s: not echoed. Not saved to shell history.
export RCLONE_AZUREBLOB_SAS_URL        # read only sets a shell variable; export passes it to rclone
[ -n "$RCLONE_AZUREBLOB_SAS_URL" ] && echo set

rclone lsd :azureblob:<container>
SRC=:azureblob:<container>/<prefix>
```

To revoke the SAS early, rotate the storage key it was signed with (`az storage account keys renew ... --key primary`).

### 3. Copy and verify

```bash
DST=kopah:gaia/<prefix>
rclone size $SRC                     # check size first: egress is ~$0.09/GB on AWS, ~$0.087/GB on Azure

rclone copy $SRC $DST \
  --transfers 16 --checkers 32 --s3-chunk-size 64M \
  --s3-no-check-bucket --s3-storage-class STANDARD \
  --low-level-retries 20 --retries 5 \
  --progress --log-file ~/rclone-copy.log --log-level INFO

rclone check $SRC $DST --one-way --s3-no-check-bucket    # prints only differences
unset RCLONE_AZUREBLOB_SAS_URL       # when finished
```

- `rclone copy src/dir dst/dir` copies the *contents* of `dir`. Keep the folder name on the destination too, or the files land loose in the parent.
- To copy one folder at a time, run it per folder. Add `--max-depth 1` to copy only the top-level files.
- `--s3-no-check-bucket` stops rclone from trying to create `gaia`, which already exists.
- To check errors: `grep -E "ERROR|NOTICE" ~/rclone-copy.log | head`.

### Gotcha: Azure → Kopah needs `--s3-storage-class STANDARD`

Without it, every upload from Azure fails, even though Azure→local and local→Kopah copies work fine:

```
ERROR : file.tif: Failed to copy: operation error S3: PutObject, exceeded maximum number of attempts, 1,
https response error StatusCode: 502 ... error while deserializing xml error response : XML syntax error on line 11: element <hr> closed by </body>
```

Transfers sit at 0% until the Kopah gateway times out with a 500/502 HTML page. With `--s3-upload-cutoff 0`, the multipart init fails instead with `400 InvalidArgument: UnknownError`. The cause: rclone carries the Azure blob's access tier (`Hot`) over as the S3 storage class, and Ceph RGW rejects it. `--s3-storage-class STANDARD` overrides it. `--s3-use-unsigned-payload` and `--s3-use-data-integrity-protections false` don't help. The flag is harmless for AWS sources, so just always pass it.

Remember that anything copied under `gaia/public/` is readable by anyone (see [Public prefixes](#public-prefixes-bucket-policy)).


## Lifecycle policies

A lifecycle policy is a nice way to work with 'scratch' data that you don't want to keep around forever. You can set up rules to automatically delete objects after a certain period of time, which can help manage storage costs and keep your bucket organized. As far as I can tell you need to use the aws cli for this rather than s3cmd/s5cmd/rclone...

### Setup AWS CLI

Put the following in your `~/.aws/credentials` file (replace with your keys):

```
[kopah]
aws_access_key_id = <Kopah ACCESS KEY>
aws_secret_access_key = <Kopah SECRET KEY>
```

Then the following `~/.aws/config` setup is apparently necessary for compatibility with Kopah Ceph filesystem and awscli>2.22.0:

```
[kopah]
endpoint_url = https://s3.kopah.uw.edu
request_checksum_calculation = when_required
response_checksum_validation = when_required
s3 =
    payload_signing_enabled = false
    checksum_algorithm = crc32
```

test with:
```
aws s3 ls s3://gaia --profile kopah
```

or with:

```
export AWS_PROFILE=kopah
aws s3 cp README.txt s3://gaia/README.txt
```

#### Add a lifecycle policy for scratch data (delete after 30 days, or 1 day for more temporary data)

The live rules for `gaia` are tracked as [`gaia-lifecycle.json`](gaia-lifecycle.json):

- `scratch-1d`: objects under `scratch-1d/` are deleted after 1 day
- `scratch-30d`: objects under `scratch/` are deleted after 30 days
- `abort-incomplete-uploads-7d`: incomplete multipart uploads anywhere in the bucket are aborted
  after 7 days. They count against the quota but are invisible to `ls` (see
  [Tracking usage](#tracking-usage-1-tib-quota)).

Like bucket policies, `put-bucket-lifecycle-configuration` **replaces** the whole configuration, so
edit the file and apply all of it:

```
aws s3api put-bucket-lifecycle-configuration --bucket gaia --profile kopah \
  --lifecycle-configuration file://docs/gaia-lifecycle.json
```

Put a file under that prefix and it should be gone a day later!
```
aws s3 cp README.md s3://gaia/scratch-1d/README.md --profile kopah
```

test with `aws s3api get-bucket-lifecycle-configuration --bucket gaia`


### Anonymous read access

```bash
aws --endpoint-url https://s3.kopah.uw.edu s3api put-bucket-policy --bucket tacolab --policy file://policy-public-read.json`

# add a simple text file to test
echo 'Hello World!' > README.txt
aws s3 cp README.txt s3://tacolab/

# Confirm public read
curl https://s3.kopah.uw.edu/tacolab/README.txt
```
## Public prefixes (bucket policy)

Kopah is [Ceph RGW](https://docs.ceph.com/en/latest/radosgw/bucketpolicy/), which supports S3 bucket
policies with `"Principal": "*"`. That lets you expose a single prefix of an otherwise private bucket
so anyone can read it over plain HTTPS, no credentials required.

**Bucket policies replace, they don't merge.** `put-bucket-policy` overwrites the entire document, so
always read the current policy first and add your statements to it — otherwise you silently revoke
someone else's public prefix:

```
aws s3api get-bucket-policy --bucket gaia --query Policy --output text > gaia-policy.json
```

Two statements per public prefix: `s3:GetObject` on the objects, and (optionally) `s3:ListBucket` on
the *bucket* with an `s3:prefix` condition so anonymous users can enumerate what's there.

The live policy is tracked in this repo as [`gaia-policy.json`](gaia-policy.json) — it currently
exposes `bkerns/public/`, `public/` and `scratch/public/`. Adding someone's prefix means editing that file (two new
statements) and applying it, so the change shows up as a reviewable git diff:

```
aws s3api put-bucket-policy --bucket gaia --policy file://docs/gaia-policy.json
```

Verify it round-tripped:

```
aws s3api get-bucket-policy --bucket gaia --query Policy --output text | jq .
```

Anything you put under `s3://gaia/public/` is then a public URL. **Path-style only** —
`https://gaia.s3.kopah.uw.edu/...` (virtual-host style) does not resolve:

```
aws s3 cp USGS_1M_12_x76y426_CO_WestCentral_2019_A19.tif s3://gaia/public/ --profile kopah
```

```
# 200, no credentials, and Accept-Ranges: bytes
curl -O https://s3.kopah.uw.edu/gaia/public/USGS_1M_12_x76y426_CO_WestCentral_2019_A19.tif

# 200, XML listing of the prefix
curl "https://s3.kopah.uw.edu/gaia?list-type=2&prefix=public/"

# 403, the rest of the bucket is still private
curl -O https://s3.kopah.uw.edu/gaia/README.txt
```

### Reading public COGs / Zarr

Range requests work (`Accept-Ranges: bytes`), so GDAL and friends stream just the bytes they need — no
credentials, no download. The example above is a USGS 3DEP 1m DEM tile: 10012x10012 Float32, LZW,
256x256 internal tiles with 5 overview levels, i.e. a proper COG.

```python
import rioxarray

url = "https://s3.kopah.uw.edu/gaia/public/USGS_1M_12_x76y426_CO_WestCentral_2019_A19.tif"
da = rioxarray.open_rasterio(url, masked=True)   # NAD83 / UTM 12N (EPSG:26912)
```

Or straight from the CLI:

```
export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
gdalinfo /vsicurl/https://s3.kopah.uw.edu/gaia/public/USGS_1M_12_x76y426_CO_WestCentral_2019_A19.tif
```

That env var matters here. Without it GDAL probes for ~30 sidecar files (`.aux.xml`, `.ovr`, `.msk`,
...) before opening the image, and Kopah answers each miss with a **403 rather than a 404** — so you
get a screen of scary-looking `HTTP response code ... 403` warnings even though the read succeeds.
Setting it to `EMPTY_DIR` skips the probing entirely and is faster besides.

If you'd rather go through the S3 driver than plain https, `AWS_NO_SIGN_REQUEST=YES` plus
`AWS_S3_ENDPOINT=s3.kopah.uw.edu` reads the same object as `/vsis3/gaia/public/...`.

**A bucket policy is not CORS.** Server-side readers don't care, but a browser client fetching the URL
directly (deck.gl, a JS COG viewer, STAC Browser) also needs CORS — see below.

## CORS (browser access)

The bucket policy decides *whether* an anonymous request may read an object. CORS is a separate
question: whether a web page served from some *other* origin may see the response. `curl`, GDAL and
Python don't care about CORS. Browser apps that `fetch()` the file themselves do care, for example
[STAC Browser](https://radiantearth.github.io/stac-browser/), stacmap, deck.gl or a JS COG viewer.
Without a CORS config the request succeeds on the wire, but the browser hides the response from the
page and logs a CORS error.

A bucket with no CORS configuration (as `gaia` was before 2026-10-14) fails like this. A GET with an `Origin` header returns no
`Access-Control-Allow-Origin` header, and the preflight `OPTIONS` returns 403:

```
curl -sI -H "Origin: https://radiantearth.github.io" \
  https://s3.kopah.uw.edu/gaia/public/prism/collection.json | grep -i access-control   # nothing

aws s3api get-bucket-cors --bucket gaia --profile kopah
# An error occurred (NoSuchCORSConfiguration) ...
```

### Bucket-wide, not per-prefix

S3 CORS (and Ceph RGW's implementation of it) is configured **per bucket**. A CORS rule matches on
origin, method and headers. It has no `Prefix` filter like lifecycle rules do, so a rule covers every
key in `gaia`.

That's fine, because **CORS grants no access**. It only tells the browser that a page may read a
response the server was already going to send. Anonymous requests for private keys still get 403
from the bucket policy, with or without CORS. So "GET/HEAD from any origin" on the whole bucket
exposes exactly what the bucket policy already makes public (`public/`, `bkerns/public/`,
`scratch/public/`) and nothing else. Leave write methods (`PUT`, `POST`, `DELETE`) out.

### Apply it

Like the bucket policy, `put-bucket-cors` **replaces** the whole CORS config, so back up whatever is
there first (`get-bucket-cors > backup.json`). The rule is tracked here as
[`gaia-cors.json`](gaia-cors.json). It was applied on 2026-10-14; `gaia` had no CORS config before
that, so there's nothing to roll back to except `delete-bucket-cors`.

```
aws s3api put-bucket-cors --bucket gaia --profile kopah \
  --cors-configuration file://docs/gaia-cors.json

aws s3api get-bucket-cors --bucket gaia --profile kopah
```

`AllowedHeaders: ["*"]` lets a browser send `Range` in a preflight, which COG/Zarr readers need.
`ExposeHeaders` lets JS read `Content-Range`/`Content-Length`/`ETag`, which range-reading libraries
use to work out the file size and validate caches.

### Verify

```
# Should now include Access-Control-Allow-Origin: *
curl -sI -H "Origin: https://radiantearth.github.io" \
  https://s3.kopah.uw.edu/gaia/public/prism/collection.json | grep -i access-control

# Preflight should return 200 with Access-Control-Allow-Methods
curl -si -X OPTIONS \
  -H "Origin: https://radiantearth.github.io" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: range" \
  https://s3.kopah.uw.edu/gaia/public/prism/collection.json | head -15
```

Then open the collection in STAC Browser:

https://radiantearth.github.io/stac-browser/#/external/s3.kopah.uw.edu/gaia/public/prism/collection.json

Also check the upload's content type. Objects uploaded with `aws s3 cp` / `s5cmd` without one are
served as `Content-Type: binary/octet-stream`, which `collection.json` currently is. Most STAC tools
parse it anyway, but it's cleaner to set it on upload:

```
aws s3 cp collection.json s3://gaia/public/prism/ --content-type application/json --profile kopah
```

To remove CORS again: `aws s3api delete-bucket-cors --bucket gaia --profile kopah`.

## Public scratch bucket (`gaia-scratch`)

`s3://gaia-scratch` (created 2026-11-02) is a separate bucket that is **entirely public**. Anyone can
read and list every key, and CORS is enabled for browser clients. Use it for things you want to share
quickly without editing the `gaia` bucket policy. Don't put anything private in it, and expect
objects to be deleted after 30 days (see [Lifecycle](#lifecycle)).

### Creating a bucket with the AWS CLI

`aws s3 mb s3://<bucket>` fails against Kopah with:

```
make_bucket failed: s3://gaia-scratch An error occurred (InvalidLocationConstraint) when calling the CreateBucket operation: The specified location-constraint is not valid
```

The `kopah` profile has no region, so the CLI sends a location constraint Ceph RGW doesn't recognize.
Kopah's only zonegroup is `default` (`aws s3api get-bucket-location --bucket gaia` returns
`"LocationConstraint": "default"`), so pass it explicitly:

```
aws s3api create-bucket --bucket gaia-scratch --profile kopah \
  --create-bucket-configuration LocationConstraint=default
```

(`s5cmd mb` works without this.)

### Policy and CORS

The bucket policy is [`gaia-scratch-policy.json`](gaia-scratch-policy.json): `s3:GetObject` on
`gaia-scratch/*` and `s3:ListBucket` on the bucket, both for `"Principal": "*"`. CORS reuses
[`gaia-cors.json`](gaia-cors.json).

```
aws s3api put-bucket-policy --bucket gaia-scratch --profile kopah \
  --policy file://docs/gaia-scratch-policy.json

aws s3api put-bucket-cors --bucket gaia-scratch --profile kopah \
  --cors-configuration file://docs/gaia-cors.json
```

### Lifecycle

Every object in `gaia-scratch` is deleted 30 days after upload (the bucket is not versioned, so
this is a real delete). Incomplete multipart uploads are aborted after 7 days.

```
aws s3api put-bucket-lifecycle-configuration --bucket gaia-scratch --profile kopah \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "expire-30d",
        "Status": "Enabled",
        "Filter": {"Prefix": ""},
        "Expiration": {"Days": 30},
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}
      }
    ]
  }'

aws s3api get-bucket-lifecycle-configuration --bucket gaia-scratch --profile kopah
```

### Verify

```
# 200, no credentials
curl https://s3.kopah.uw.edu/gaia-scratch/README.txt

# 200, XML listing of the whole bucket
curl "https://s3.kopah.uw.edu/gaia-scratch?list-type=2"

# Access-Control-Allow-Origin: *
curl -sI -H "Origin: https://example.com" \
  https://s3.kopah.uw.edu/gaia-scratch/README.txt | grep -i access-control
```

## Temporary access (presigned URLs)

To give someone time-limited access to a private object without sharing keys, use a presigned URL.
This is the S3 equivalent of an Azure SAS URL. The URL is signed locally with your Kopah key, and
Kopah checks the signature and the expiry. Tested on 2026-11-24:

| What | Result on Kopah |
|---|---|
| Presigned GET of a private object | Works. 200 with the URL, 403 without it, 403 if the signature is altered |
| Longest expiry | **7 days** (604800 s, the SigV4 limit). An 8-day URL is rejected with `AccessDenied` |
| Presigned PUT (upload) | Works, but only for the one key it was signed for. The same URL for another key gets 403 |
| STS (`GetSessionToken`, `AssumeRole`) | `AccessDenied`: no temporary scoped credentials |
| IAM (`ListRoles`, `ListUsers`) | `AccessDenied` |

### Download link

```bash
aws s3 presign s3://gaia/path/to/file.tif --expires-in 86400 --profile kopah   # 1 day; max 604800
```

Range requests work on the presigned URL, so GDAL can stream a private COG over `/vsicurl/` without
downloading it. Quote the URL in the shell, because it contains `&`.

### Upload link

`aws s3 presign` only makes GET URLs. For a PUT URL, use boto3:

```python
# uv run --with boto3 python presign_put.py
import boto3

s3 = boto3.Session(profile_name="kopah").client(
    "s3", endpoint_url="https://s3.kopah.uw.edu", region_name="default"
)
url = s3.generate_presigned_url(
    "put_object", Params={"Bucket": "gaia", "Key": "incoming/data.nc"}, ExpiresIn=3600
)
print(url)
```

The recipient uploads with no credentials:

```bash
curl -X PUT --upload-file data.nc "$URL"
```

If you pass `ContentType` in `Params`, the uploader must send exactly that `Content-Type` header, or the
signature won't match.

### Limits

- **Write access is per object, not per prefix.** STS is not available to Kopah tenants, so there is
  no time-limited, prefix-scoped key like an Azure container SAS or AWS STS credentials. To accept
  many files, sign one PUT URL per key. A presigned POST policy with a `starts-with $key` condition
  should allow a whole prefix (Ceph RGW supports POST policies), but it hasn't been tested on Kopah.
- **No early revocation.** A URL stays valid until it expires, unless the key that signed it is
  rotated, which likely needs UW IT. Use short expiries.
- **The URL can do whatever the signing key can do, for that one request.** Anyone who has the URL
  can use it until it expires, so treat it as a secret.
- For finer control, such as a separate key limited to one prefix, ask UW IT about enabling STS or
  creating a subuser.
