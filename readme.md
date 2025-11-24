DisasterScout
=============

**DisasterScout** is a real‑time crisis‑intelligence tool that turns live news, geocoding, and LLM reasoning into an interactive disaster map and chat‑based assistant.

It helps users quickly understand what is happening during events like floods, storms, wildfires, and infrastructure emergencies — showing **SOS zones**, **shelters**, and **general info reports** directly on a map.

### How It Works

The system automatically:

*   **Queries** Tavily for disaster‑related news.
    
*   **Filters & Cleans** results using OpenAI + custom NLP logic to classify incidents.
    
*   **Geocodes** extracted affected locations.
    
*   **Deduplicates** and stores data in MongoDB Atlas.
    
*   **Displays** incidents on a fast, interactive Leaflet map.
    
*   **Responds** to natural‑language messages (e.g., _“Flood in Brooklyn, NY”_) with summaries, guidance, and a link to the map.
    

### Tech Stack

*   **Backend:** FastAPI
    
*   **Database:** MongoDB Atlas
    
*   **Search & Intelligence:** Tavily Search API, OpenAI (classification, filtering, LLM reasoning)
    
*   **Frontend:** LeafletJS map, Simple chat UI (no framework)
    
*   **Data Pipeline:** Custom ingestion pipeline with semantic/geo deduplication
    

### How to Run

**1\. Install dependencies**

Bash

`   pip install -r requirements.txt   `

**2\. Set environment variables**Ensure the following variables are set in your environment or .env file:

*   OPENAI\_API\_KEY
    
*   TAVILY\_API\_KEY
    
*   MONGO\_URI
    
*   MONGO\_DB\_NAME
    

**3\. Start server**

Bash
`   uvicorn api_server.main:app --reload   `

**4\. Open the map UI**Navigate to: [http://localhost:8000/map](https://www.google.com/search?q=http://localhost:8000/map)

### Example Queries

You can ask the assistant queries such as:

> "Flood in Brooklyn, NY"
> 
> "Flood in Bay Ridge, Brooklyn, NY"
> 
> "Flood in Qui Nhon, Vietnam"

The assistant returns a short situation report, actionable guidance, and a button to open the map centered on that region.