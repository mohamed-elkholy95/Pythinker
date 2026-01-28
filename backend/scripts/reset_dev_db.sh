#!/bin/bash
# Reset development database - DESTRUCTIVE OPERATION
# This will drop the entire database and recreate it from scratch

set -e

echo "=========================================="
echo "  DEV DATABASE RESET"
echo "=========================================="
echo ""
echo "⚠️  WARNING: This will DELETE ALL DATA in the MongoDB database!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "📦 Loading environment variables..."

# Get MongoDB URI from .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "❌ .env file not found"
    exit 1
fi

# Default database name if not in env
DB_NAME="${MONGODB_DATABASE:-pythinker}"
MONGO_URI="${MONGODB_URI:-mongodb://localhost:27017}"

echo "Database: $DB_NAME"
echo "URI: $MONGO_URI"
echo ""

# Drop the database using mongosh or mongo
echo "🗑️  Dropping database '$DB_NAME'..."

if command -v mongosh &> /dev/null; then
    # Use mongosh (MongoDB 5.0+)
    mongosh "$MONGO_URI/$DB_NAME" --eval "db.dropDatabase()" --quiet
elif command -v mongo &> /dev/null; then
    # Use legacy mongo client
    mongo "$MONGO_URI/$DB_NAME" --eval "db.dropDatabase()" --quiet
else
    echo "❌ MongoDB client (mongosh or mongo) not found"
    echo "Please install MongoDB client tools or drop the database manually"
    exit 1
fi

echo "✅ Database dropped"
echo ""

# Reinitialize the schema
echo "🔧 Initializing fresh schema..."
cd "$(dirname "$0")/.."
python scripts/init_mongodb.py

echo ""
echo "=========================================="
echo "✅ Database reset complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Start the backend: ./dev.sh up -d"
echo "  2. Create a test user via API"
echo "  3. Start developing!"
echo ""
