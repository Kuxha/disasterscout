from pymongo import MongoClient
from dotenv import load_dotenv
import os

def main():
    load_dotenv()
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "disaster_db")

    client = MongoClient(mongo_uri)
    db = client[db_name]

    # Create 2dsphere index
    print("Creating 2dsphere geospatial index...")
    db.incidents.create_index([("location", "2dsphere")])
    print("Done!")

if __name__ == "__main__":
    main()
