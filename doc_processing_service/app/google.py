import os
from fastapi import FastAPI, File, UploadFile, HTTPException
from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from typing import List, Dict, Any

app = FastAPI()

# --- 1. Konfiguration aus Umgebungsvariablen laden ---
# Diese müssen in Ihrer Laufzeitumgebung gesetzt sein (z.B. Docker-Compose, Kubernetes, etc.)
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION")  # z.B. 'eu' oder 'us'
PROCESSOR_ID = os.getenv("PROCESSOR_ID")

# Überprüfen, ob die Konfiguration vorhanden ist
if not all([GCP_PROJECT_ID, GCP_LOCATION, PROCESSOR_ID]):
    raise RuntimeError("Die Umgebungsvariablen GCP_PROJECT_ID, GCP_LOCATION und PROCESSOR_ID müssen gesetzt sein.")

# --- 2. Hilfsfunktion zur Formatierung der Bounding Box ---
def format_bounding_box(bounding_poly: documentai.BoundingPoly) -> List[int]:
    """
    Konvertiert das BoundingPoly-Format von Document AI in eine einfache [xmin, ymin, xmax, ymax] Liste.
    Die Koordinaten sind bereits auf den Bereich 0-1 normalisiert. Wir skalieren sie auf 0-1000 für Konsistenz.
    """
    vertices = bounding_poly.normalized_vertices
    if not vertices:
        return [0, 0, 0, 0]
        
    x_coords = [v.x * 1000 for v in vertices]
    y_coords = [v.y * 1000 for v in vertices]
    
    return [int(min(x_coords)), int(min(y_coords)), int(max(x_coords)), int(max(y_coords))]

# --- 3. FastAPI Endpoint ---
@app.post("/process_pdf/")
async def process_pdf_endpoint(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF is accepted.")

    try:
        pdf_bytes = await file.read()

        # Document AI Client initialisieren
        # Der regionale Endpunkt muss explizit gesetzt werden
        opts = ClientOptions(api_endpoint=f"{GCP_LOCATION}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)

        # Vollständiger Name des Prozessors
        processor_name = client.processor_path(GCP_PROJECT_ID, GCP_LOCATION, PROCESSOR_ID)

        # Dokumentobjekt erstellen, das an die API gesendet wird
        raw_document = documentai.RawDocument(
            content=pdf_bytes,
            mime_type="application/pdf",
        )

        # API-Aufruf zur Verarbeitung des Dokuments
        print(f"Sending document to Document AI processor: {processor_name}")
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
        result = client.process_document(request=request)
        document = result.document
        print("Document AI processing complete.")

        # Ergebnisse pro Seite strukturieren
        page_features: Dict[int, List] = {}

        # Durch die extrahierten Entitäten des Dokuments iterieren
        for entity in document.entities:
            # Jede Entität hat einen Anker, der auf eine Seite und Bounding Box verweist
            page_ref = entity.page_anchor.page_refs[0]
            page_number = int(page_ref.page) + 1  # Document AI ist 0-indiziert

            if page_number not in page_features:
                page_features[page_number] = []
            
            # Die extrahierten Daten sammeln
            page_features[page_number].append({
                "text": entity.mention_text,
                "label": entity.type_,  # Das ist der Name des Feldes, z.B. 'name', 'address'
                "confidence": entity.confidence,
                "box": format_bounding_box(page_ref.bounding_poly),
            })

        # Die finale Ergebnisstruktur erstellen
        results = [
            {"page_number": pn, "features": features}
            for pn, features in sorted(page_features.items())
        ]
        
        print(f"Found features on {len(results)} pages.")
        return {"filename": file.filename, "results": results}

    except Exception as e:
        print(f"An error occurred during Document AI processing: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process document with Google Document AI: {str(e)}")


@app.get("/health")
async def health_check():
    # Der Health-Check prüft jetzt nur noch, ob die Konfiguration geladen ist
    return {"status": "healthy", "config_loaded": bool(GCP_PROJECT_ID)}