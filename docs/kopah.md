# Kopah

UW Hyak now provides a managed object store called Kopah

https://hyak.uw.edu/docs/storage/kopah

https://github.com/maouw/kopah-uw-s3api-test

You must apply for a trial account or pay-as-you go storage. Here's a current price comparison for blob storage options (as of 05/2026):

| Storage | Cost/TB/mo | Egress | Commitment |
|---|---|---|---|
| **[UW Kopah](https://hyak.uw.edu/docs/storage/kopah)** | $5.04 | Free | Month-to-month |
| **[Backblaze B2](https://www.backblaze.com/cloud-storage)** | $6.00 | Free (via Cloudflare) | None |
| **[Cloudflare R2](https://www.cloudflare.com/developer-platform/r2/)** | $15.00 | Free | None |
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

The following `~/.aws/config` setup is apparently necessary for compatibility with Kopah Ceph filesystem and awscli>2.22.0:

```
[default]
endpoint_url = https://s3.kopah.uw.edu
request_checksum_calculation = when_required
response_checksum_validation = when_required
s3 =
    payload_signing_enabled = false
    checksum_algorithm = crc32
```

test with `aws s3 cp README.txt s3://gaia/README.txt`

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

test with `aws s3api get-bucket-lifecycle-configuration --bucket gaia`
