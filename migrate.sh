#!/bin/sh

# Requires the FileMaker Data Migration Tool (https://community.claris.com/en/s/article/FileMaker-data-migration-tool)

# Context
cd "$(dirname "$0")"
[ -f .env ] && source .env

if [ "$1" = "-h" ]; then
    echo "Use $0 [solution]"
    echo Migrates solution_prod.fmp12 using clone solution_dev.fmp12 into solution.fmp12
fi

# Validate
if [ -z "$SOLUTION" ] && [ -z "$1" ]; then
    echo Solution missing in .env, alternatively input it as a parameter
    echo "use $0 <solution>"
fi

read -p "Username: " USERNAME
read -sp "Password: " PASSWORD

# Migrate
FMDataMigration -src_path "${SOLUTION}_prod.fmp12" -src_account "$USERNAME" -src_pwd "$PASSWORD" \
    -clone_path "${SOLUTION}_dev.fmp12" -clone_account "$USERNAME" -clone_pwd "$PASSWORD" \
    -target_path "./$SOLUTION.fmp12" -ignore_valuelists -ignore_accounts -v > migration.log

