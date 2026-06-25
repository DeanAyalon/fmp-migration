# AWS IAM for migration S3 access
The migration service downloads a FileMaker clone file from S3 before copying it into the FileMaker Server container. It needs a dedicated IAM principal with read-only access to that single object.

## Principal
Create a dedicated IAM user and generate access keys for it. Store the keys in one of two places:
- `.env` as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION`
- `~/.aws/credentials` on the host, with `~/.aws` mounted read-only into the migration container

Use one credential method, not both.

## Policy
Attach a least-privilege inline or custom managed policy. Required permissions:
- `s3:GetObject` on `arn:aws:s3:::${BUCKET}/${SOLUTION}_clone.fmp12` — download the clone file

Replace `BUCKET_NAME` and `SOLUTION_PREFIX` in the example below before attaching:

```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Sid": "GetCloneObject",
        "Effect": "Allow",
        "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12"
    }]
}
```

## Setup
For development, you can use `aws login` with your full access account while mounting `~/.aws` into the container.

For production, create a dedicated IAM user:
1. Open [IAM → Policies](https://console.aws.amazon.com/iamv2/home#/policies), click **Create policy**, choose the **JSON** tab, and paste the policy above (with placeholders substituted).
2. Open [IAM → Users](https://console.aws.amazon.com/iamv2/home#/users) and click **Create user** for the migration service.
3. Attach the policy to the user (Permissions step during user creation, or on the user's **Permissions** tab afterward).
4. Open the user from [IAM → Users](https://console.aws.amazon.com/iamv2/home#/users), go to **Security credentials**, and click **Create access key**.
5. Map `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION` in `.env`.

Use either method at your own discretion.

## Verification
Using the new principal's credentials:
```bash
aws s3 cp s3://BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12 /dev/null
```
The copy to `/dev/null` confirms `GetObject` without writing a local file.
