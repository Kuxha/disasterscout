from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME", "disaster_db")]

embedding_query = [0.01, 0.02, 0.03]  # dummy small vector

pipeline = [
    {
        "$search": {
            "knnBeta": {
                "vector": embedding_query,
                "path": "embedding",
                "k": 3
            }
        }
    },
    {"$limit": 3}
]

print("Running vector search…")
results = list(db.incidents.aggregate(pipeline))
print(results)
