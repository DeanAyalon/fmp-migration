#!/bin/sh

# Requires the FileMaker Data Migration Tool (https://community.claris.com/en/s/article/FileMaker-data-migration-tool)

# Context
cd "$(dirname "$0")"
[ -f .env ] && source .env
# Validate
if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
    echo Credentials missing in .env
    exit 1
elif [ -z "$2" ]; then 
    echo Please specify source and clone paths
    exit 1
fi
[ -z "$SOLUTION" ] && SOLUTION=merged

# Migrate
FMDataMigration -src_path "$1" -src_account $USERNAME -src_pwd $PASSWORD \
    -clone_path "$2" -clone_account $USERNAME -clone_pwd $PASSWORD \
    -target_path ./$SOLUTION.fmp12 -ignore_valuelists -ignore_accounts -v > migration.log

