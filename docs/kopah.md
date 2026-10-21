# Kopah

UW Hyak now provides a managed object store called Kopah

https://hyak.uw.edu/docs/storage/kopah

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

```
aws s3api put-bucket-lifecycle-configuration \
  --bucket gaia \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "scratch-30d",
        "Status": "Enabled",
        "Filter": {"Prefix": "scratch/"},
        "Expiration": {"Days": 30}
      },
      {
        "ID": "scratch-1d",
        "Status": "Enabled",
        "Filter": {"Prefix": "scratch-1d/"},
        "Expiration": {"Days": 1}
      }
    ]
  }'
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

The policy as it stood before `public/` was added is kept here as
[`gaia-policy.backup.json`](gaia-policy.backup.json), in case you need to roll back.

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
