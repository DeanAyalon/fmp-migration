# AWS IAM for migration S3 access

The migration service downloads a FileMaker clone file from S3 before copying it into the FileMaker Server container. It needs a dedicated IAM principal with read-only access to that single object (and limited list access on the bucket prefix).

## Principal

Create a dedicated **IAM user** and generate access keys for it. Store the keys in one of two places:

- `.env` as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION`
- `~/.aws/credentials` on the host, with `~/.aws` mounted read-only into the migration container

Use one credential method, not both.

## Policy

Attach a least-privilege inline or custom managed policy. Required permissions:

- `s3:ListBucket` on `arn:aws:s3:::${BUCKET}` — scoped to the clone prefix when practical
- `s3:GetObject` on `arn:aws:s3:::${BUCKET}/${SOLUTION}_clone.fmp12` — download the clone file

Replace `BUCKET_NAME` and `SOLUTION_PREFIX` in the example below before attaching:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ListBucketForClone",
            "Effect": "Allow",
            "Action": ["s3:ListBucket"],
            "Resource": "arn:aws:s3:::BUCKET_NAME",
            "Condition": {
                "StringLike": {
                    "s3:prefix": ["SOLUTION_PREFIX_*"]
                }
            }
        },
        {
            "Sid": "GetCloneObject",
            "Effect": "Allow",
            "Action": ["s3:GetObject"],
            "Resource": "arn:aws:s3:::BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12"
        }
    ]
}
```

## Setup

1. Create the policy in IAM (JSON above, with placeholders substituted).
2. Create an IAM user for the migration service.
3. Attach the policy to the user.
4. Create an access key for the user.
5. Configure credentials:
   - Map `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION` in `.env`, **or**
   - Add the keys to `~/.aws/credentials` and mount `~/.aws` into the container.

## Verification

Using the new principal's credentials:

```bash
aws s3 ls s3://BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12
aws s3 cp s3://BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12 /dev/null
```

The list command confirms the object exists and is visible. The copy to `/dev/null` confirms `GetObject` without writing a local file.
