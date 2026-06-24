# Prompt log: migration_http_service_298d7df6

Plan a python service that listens on a single http endpoint, matching auth token from .env

dockerized from the start with compose.yml and develop tag for compose watch

When it gets an authenticate call, it should use `aws s3 cp $BUCKET:$SOLUTION_clone.fmp12 ./staging`

It should have the docker.sock mounted
Then it should `docker cp ./staging/$SOLUTION_clone.fmp12 $FMS_CONTAINER:/tmp/migration/clone.fmp12`

and then `docker exec $FMS_CONTAINER <some commands I will define later>`

DO NOT BROWSE THE OTHER FUCKING BRANCHES, THIS IS A NEW PROJECT

**Q:** Where does SOLUTION come from for the S3 key `{SOLUTION}_clone.fmp12`?
**A:** Fixed in .env (one solution per deployment)

**Q:** How should the HTTP endpoint validate the auth token from .env?
**A:** Authorization: Bearer <token>

---
If a migration is already running, additional requests will be blocked

---
When creating the aws step, make a readme describing the iam creation and permissions, allow list files in bucket, avoid useless stuff like docker commands as I know those, just what I asked for

---
be explicit about either mounting .aws or using aws credential env vars, not anything else

---
the /authenticate endpoint is not used for authentication but for starting a migration process, hence, alter plan and name it accordingly

---
alter plan, dockerization should be next step (second)
