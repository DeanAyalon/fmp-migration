#!/bin/sh

# Requires the FileMaker Data Migration Tool (https://community.claris.com/en/s/article/FileMaker-data-migration-tool)

# Context
cd "$(dirname "$0")"
[ -f .env ] && source .env

# Utils
help() {
    if [ -z "$SOLUTION" ]; then 
        echo "Use $0 <source path> <clone path> <migrated path>"
        echo
        echo "  e.g. $0 ./solution.fmp12 ./solution_dev.fmp12 ./solution_migrated.fmp"
        echo '  Migrates from source solution.fmp12 using clone solution_dev.fmp12 into solution_migrated.fmp12'
        echo
        echo
        echo Alternatively, you can set a 'SOLUTION' parameter within .env and run:
        help_solution SOLUTION
        echo
        echo "To create .env, you can run:    echo SOLUTION=myapp > $(dirname "$0")/.env"
    else 
        printf "Use: "
        help_solution $SOLUTION
        echo
        echo SOLUTION is set in .env to $SOLUTION
    fi
    exit $1
}
help_solution() {
    echo "$0 <source suffix> <clone suffix> [migrated suffix]"
    echo
    echo "  e.g. $0 prod dev"
    echo "  Migrates from source ${1}_prod.fmp12 using clone ${1}_dev.fmp12 into ${1}_migrated.fmp12"
}   
fail() {
    echo $@
    exit 1
}

# Validate
[ "$1" = "-h" ] && help 0
[ -z "$2" ] && help 1
[ -z "$SOLUTION" ] && [ -z "$3" ] && help 1
migrated=${3:-migrated}
# Check FMDataMigration
FMDataMigration -version &> /dev/null || fail "Please install the FMDataMigrationTool: https://community.claris.com/en/s/article/FileMaker-data-migration-tool"

# Credentials prompt
read -p "Username: " USERNAME
read -sp "Password: " PASSWORD

# Migrate
if [ -z "$SOLUTION" ]; then 
    FMDataMigration -src_path "$1" -src_account $USERNAME -src_pwd "$PASSWORD" \
        -clone_path "$2" -clone_account $USERNAME -clone_pwd "$PASSWORD" \
        -target_path "$3" -ignore_valuelists -ignore_accounts -v > migration.log
else
    FMDataMigration -src_path "${SOLUTION}_$1.fmp12" -src_account $USERNAME -src_pwd "$PASSWORD" \
        -clone_path "${SOLUTION}_$2.fmp12" -clone_account $USERNAME -clone_pwd "$PASSWORD" \
        -target_path "${SOLUTION}_$migrated.fmp12" -ignore_valuelists -ignore_accounts -v > migration.log
fi

# Unset from memory to be safe in case the script is sourced
unset PASSWORD
