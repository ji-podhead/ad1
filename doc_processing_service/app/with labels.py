import os
from fastapi import FastAPI, File, UploadFile, HTTPException
from PIL import Image
import pdf2image
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
import torch
import io
from typing import List, Dict, Any

# --- FIX 1: Unterdrückt die Tokenizer-Parallelismus-Warnung ---
# Dies sollte ganz am Anfang der Datei stehen, vor den transformers-Imports.
os.environ["TOKENIZERS_PARALLELISM"] = "false"


app = FastAPI()

# Load Model and Processor
try:
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-large", apply_ocr=True)
    model = LayoutLMv3ForTokenClassification.from_pretrained("microsoft/layoutlmv3-large")
    model.eval() 
except Exception as e:
    print(f"Error loading model or processor: {e}")
    processor = None
    model = None

# Die Hilfsfunktionen (normalize_box, group_entities) bleiben unverändert.
# ... (fügen Sie hier die Funktionen 'normalize_box' und 'group_entities' aus meiner vorherigen Antwort ein) ...

def normalize_box(box, width, height):
    """Normalisiert die Bounding Box Koordinaten auf einen Bereich von 0-1000."""
    return [
        int(1000 * (box[0] / width)),
        int(1000 * (box[1] / height)),
        int(1000 * (box[2] / width)),
        int(1000 * (box[3] / height)),
    ]

def group_entities(tokens: List[str], boxes: List[List[int]], predictions: List[int], id2label: Dict[int, str]) -> List[Dict[str, Any]]:
    """
    Gruppiert Tokens basierend auf dem B-I-O-Schema zu zusammenhängenden Entitäten.
    """
    entities = []
    current_entity_tokens = []
    current_entity_boxes = []
    current_entity_label = None

    for token, box, pred_id in zip(tokens, boxes, predictions):
        label = id2label[pred_id]
        print(f"Token: {token}, Box: {box}, Label: {label}")
        if token in [processor.tokenizer.cls_token, processor.tokenizer.sep_token]:
            continue

        if label.startswith('B-'): 
            if current_entity_label:
                x_min = min([b[0] for b in current_entity_boxes])
                y_min = min([b[1] for b in current_entity_boxes])
                x_max = max([b[2] for b in current_entity_boxes])
                y_max = max([b[3] for b in current_entity_boxes])
                
                entities.append({
                    "text": processor.tokenizer.convert_tokens_to_string(current_entity_tokens),
                    "label": current_entity_label,
                    "box": [x_min, y_min, x_max, y_max]
                })

            current_entity_tokens = [token]
            current_entity_boxes = [box]
            current_entity_label = label.replace('B-', '')

        elif label.startswith('I-') and current_entity_label == label.replace('I-', ''):
            current_entity_tokens.append(token)
            current_entity_boxes.append(box)
        
        else:
            if current_entity_label:
                x_min = min([b[0] for b in current_entity_boxes])
                y_min = min([b[1] for b in current_entity_boxes])
                x_max = max([b[2] for b in current_entity_boxes])
                y_max = max([b[3] for b in current_entity_boxes])
                
                entities.append({
                    "text": processor.tokenizer.convert_tokens_to_string(current_entity_tokens),
                    "label": current_entity_label,
                    "box": [x_min, y_min, x_max, y_max]
                })
            current_entity_tokens = []
            current_entity_boxes = []
            current_entity_label = None

    if current_entity_label:
        x_min = min([b[0] for b in current_entity_boxes])
        y_min = min([b[1] for b in current_entity_boxes])
        x_max = max([b[2] for b in current_entity_boxes])
        y_max = max([b[3] for b in current_entity_boxes])
        
        entities.append({
            "text": processor.tokenizer.convert_tokens_to_string(current_entity_tokens),
            "label": current_entity_label,
            "box": [x_min, y_min, x_max, y_max]
        })

    return entities


@app.post("/process_pdf/")
async def process_pdf_endpoint(file: UploadFile = File(...)):
    if not processor or not model:
        raise HTTPException(status_code=503, detail="Model or processor not available.")
    # ... (Rest der Funktion bis zur for-Schleife)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF is accepted.")

    try:
        pdf_bytes = await file.read()
        images = pdf2image.convert_from_bytes(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read or convert PDF: {str(e)}")

    results = []
    id2label = model.config.id2label

    for i, pil_image in enumerate(images):
        page_number = i + 1
        print(f"Processing page {page_number}...")
        
        try:
            image = pil_image.convert("RGB")
            width, height = image.size

            # encoding = processor(image, return_tensors="pt")
            encoding = processor(
                image, 
                return_tensors="pt",
                truncation=True,        # Zu lange Sequenzen abschneiden
                padding="max_length",   # Auf max_length auffüllen
                max_length=512          # Maximale Länge des Modells
            )
            # Temporäre Debug-Ausgabe:
            ocr_text = processor.tokenizer.decode(encoding.input_ids[0], skip_special_tokens=True)
            print(f"--- DEBUG OCR TEXT (Page {page_number}) ---\n{ocr_text[:1000]}...\n---------------------------------")
            encoding.pop("image", None)

            # --- FIX 2: Robusterer Umgang mit Tensor-Dimensionen ---
            # Prüfen, ob überhaupt Tokens gefunden wurden. encoding['input_ids'] hat immer die Form (1, sequence_length)
            if encoding['input_ids'].shape[1] <= 2: # Nur [CLS] und [SEP] Token, kein echter Inhalt
                print(f"Page {page_number}: No text found, skipping.")
                results.append({"page_number": page_number, "features": []})
                continue
            
            with torch.no_grad():
                outputs = model(**encoding)

            # Ersetze .squeeze() durch explizite Indexierung [0], um die Batch-Dimension zu entfernen.
            # Das ist viel sicherer und vermeidet den Fehler.
            token_predictions = outputs.logits[0].argmax(-1).tolist()
            print(f"Token predictions for page {page_number}: {token_predictions}")
            token_boxes_unnormalized = encoding.bbox[0].tolist()

            # Normalisiere die Bounding Boxen
            token_boxes = [normalize_box(box, width, height) for box in token_boxes_unnormalized]
            print(f"Token boxes for page {page_number}: {token_boxes}")
            input_ids = encoding.input_ids[0].tolist()
            tokens = processor.tokenizer.convert_ids_to_tokens(input_ids)
            
            extracted_features = group_entities(tokens, token_boxes, token_predictions, id2label)

            results.append({
                "page_number": page_number,
                "features": extracted_features
            })
            print(f"Page {page_number}: Found {len(extracted_features)} features.")

        except Exception as e:
            # Das Logging hier ist sehr wichtig, um den genauen Fehler zu sehen
            import traceback
            print(f"Error processing page {page_number}: {e}")
            traceback.print_exc() # Gibt den vollständigen Stacktrace aus
            results.append({
                "page_number": page_number,
                "error": f"Failed to process page {page_number}: {str(e)}"
            })

    return {"filename": file.filename, "results": results}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "model_loaded": bool(model and processor)}