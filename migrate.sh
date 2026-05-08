#!/bin/bash

# Uses a FileMaker Server container

# Context
cd "$(dirname "$0")"
[ -f .env ] && source .env

# Utils
help() {
    echo "Use $0 <clone path> [migrated path]"
    echo
    echo "  e.g. $0 ./solution_dev.fmp12 ./solution_migrated.fmp12"
    echo '  Migrates from source database \$SOLUTION using clone solution_dev.fmp12 into solution_migrated.fmp12'
    echo
    exit $1
}
fail() {
    echo $@
    exit 1
}

# Validate
[ "$1" = "-h" ] || [ "$1" = "help" ] && help 0
[ -z "$1" ] && help 1
migrated=${2:-migrated}
[ -z "$FMS_CONTAINER" ] && FMS_CONTAINER=fms
[ -z "$SOLUTION" ] && fail "Please set \$SOLUTION within .env"
echo Migrating $SOLUTION using $1

# source path
[ -z "$DATABASES_PATH" ] && DATABASES_PATH="/opt/FileMaker/FileMaker Server/Data/Databases"
SOURCE_PATH="$DATABASES_PATH/$SOLUTION.fmp12"

# Credentials prompt
read -p "Username: " USERNAME
read -sp "Password: " PASSWORD
echo

# Temporary folder inside container
dir=/tmp/migration
docker exec $FMS_CONTAINER mkdir -p $dir

# Copy source and clone into container
docker exec $FMS_CONTAINER cp "$SOURCE_PATH" $dir/source.fmp12
docker cp "$1" $FMS_CONTAINER:$dir/clone.fmp12

# Remove existing migrated solution
docker exec $FMS_CONTAINER rm "$dir/$SOLUTION.fmp12"

# Run migration inside container
docker exec $FMS_CONTAINER FMDataMigration \
    -src_path "$dir/source.fmp12" -src_account "$USERNAME" -src_pwd "$PASSWORD" \
    -clone_path "$dir/clone.fmp12" -clone_account "$USERNAME" -clone_pwd "$PASSWORD" \
    -target_path "$dir/$SOLUTION.fmp12" -ignore_valuelists -ignore_accounts -v | tee migration.log

docker cp $FMS_CONTAINER:$dir/$SOLUTION.fmp12 .

# Prompt to update live solution
# TODO 

# Unset from memory to be safe in case the script is sourced
unset PASSWORD
