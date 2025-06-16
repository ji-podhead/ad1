import os
from fastapi import FastAPI, File, UploadFile, HTTPException
from PIL import Image, ImageDraw, ImageFont # Import ImageDraw and ImageFont
import pdf2image
import io
from typing import List, Dict, Any
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
# Import Surya predictors
from surya.layout import LayoutPredictor
from surya.table_rec import TableRecPredictor
from surya.recognition import RecognitionPredictor
from surya.detection import DetectionPredictor
import pytest
import httpx
import asyncio
import os
import json # Import json for LLM response parsing
from pydantic import BaseModel # Import BaseModel from pydantic
from pydantic_ai import Agent # Import Agent from pydantic_ai
from pydantic_ai.models.gemini import GeminiModel, GeminiModelSettings # Import GeminiModel and Settings
import logging # Added for explicit logging
from typing import Optional # Import Optional


import pytest
import httpx
import asyncio
import os
# --- FIX 1: Unterdrückt die Tokenizer-Parallelismus-Warnung ---
# This might not be relevant for Surya, but can be kept for now.
os.environ["TOKENIZERS_PARALLELISM"] = "false"


app = FastAPI()

# Load Surya Predictors Globally
try:
    layout_predictor_surya = LayoutPredictor()
    table_rec_predictor_surya = TableRecPredictor()
    print("Surya predictors loaded successfully.")
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=True) # Changed to True
    model = LayoutLMv3ForTokenClassification.from_pretrained("microsoft/layoutlmv3-base")
    model.eval() # Set model to evaluation mode
except Exception as e:
    print(f"Error loading Surya predictors: {e}")
    layout_predictor_surya = None
    table_rec_predictor_surya = None
    print(f"Error loading model or processor: {e}")
    # Depending on policy, you might want to raise an exception here to stop the app from starting
    # or allow it to start and fail on endpoint usage.
    processor = None
    model = None

# Remove LayoutLMv3 specific helper functions: normalize_box and group_entities
# def normalize_box(...): ...
# def group_entities(...): ...
recognition_predictor = RecognitionPredictor()

def extract_text_from_box(image, box):
    # Extrahieren Sie das Bildausschnitt basierend auf der Box
    x1, y1, x2, y2 = box.bbox
    crop = image.crop((x1, y1, x2, y2))
    encoding = processor(crop, return_tensors="pt", truncation=True, padding="max_length", max_length=512)
    ocr_token_ids = encoding['input_ids'][0]
    tex = processor.tokenizer.decode(ocr_token_ids, skip_special_tokens=True)
    print(f"Extracted text: {tex[:30]}...")
    return tex

def boxes_overlap(bbox1, bbox2):
    x1, y1, x2, y2 = bbox1
    x3, y3, x4, y4 = bbox2
    return not (x2 < x3 or x1 > x4 or y2 < y3 or y1 > y4)

@app.post("/process_pdf/")
async def process_pdf_endpoint(file: UploadFile = File(...)):
    if not layout_predictor_surya or not table_rec_predictor_surya:
        raise HTTPException(status_code=503, detail="Surya predictors not available. Check server logs.")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF is accepted.")

    try:
        pdf_bytes = await file.read()
        # dpi=300 was added previously, keeping it as it's good for OCR quality
        pil_images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read or convert PDF: {str(e)}")

    if not pil_images:
        print("No images extracted from PDF.")
        return {"filename": file.filename, "results": []}
    
    print(f"Converted PDF to {len(pil_images)} images. Processing with Surya...")

    page_results = []

    try:
        # Get layout predictions for all images
        print(f"Running layout detection for {len(pil_images)} images...")
        layout_predictions = layout_predictor_surya(pil_images)
        print("Layout detection complete.")

        # Get table predictions for all images
        print(f"Running table recognition for {len(pil_images)} images...")
        table_predictions = table_rec_predictor_surya(pil_images)
        print("Table recognition complete.")

        for i, _ in enumerate(pil_images):
            page_number = i + 1
            
            # Surya's output is a list of results, one per image
            current_page_layout = layout_predictions[i] if i < len(layout_predictions) else {}
            current_page_tables = table_predictions[i] if i < len(table_predictions) else {}
            
            # page_results.append({
            #     "page_number": page_number,
            #     "layout_analysis": current_page_layout, # Contains bboxes, polygons, labels, etc.
            #     "table_analysis": current_page_tables   # Contains rows, cols, cells, etc.
            # })
            page_results.append({
            "page_number": i + 1,
            "elements": []
            })
              # Verarbeite jede Box auf der Seite
         
        for i, _ in enumerate(pil_images):
            page_number = i + 1
            # Surya's output is a list of results, one per image
            current_page_layout = layout_predictions[i] if i < len(layout_predictions) else {}
            current_page_tables = table_predictions[i] if i < len(table_predictions) else {}
            page_results.append({
                "page_number": page_number,
                "elements": []
            })
            
            # Verarbeite jede Box auf der Seite
            for box in current_page_layout.bboxes:
                print(f"Processing box on page {page_number}: {box}")
                element = {
                    'bbox': box.bbox,
                    'polygon': box.polygon,
                    'label': box.label,
                    "position":box.position,
                    "top_k":box.top_k,
                    "confidence":box.confidence,
                    "bbox":box.bbox
                }
                
                if box.label == 'Text':
                    # Extrahiere Text aus der Box
                    text_lines = extract_text_from_box(pil_images[i], box)
                    element['text'] = text_lines
                elif box.label == 'Table':
                    # Finde die entsprechende Tabellenanalyse
                    matching_table = None
                    for table in current_page_tables.cells:
                        print(table)
                        if boxes_overlap(box.bbox, table.bbox):
                            matching_table = table
                            break
                    if matching_table:
                        element['table_data'] = {
                          "confidence":table.confidence,
                          "row_id":table.row_id,
                          "colspan":table.colspan,
                          "within_row_id": table.within_row_id,
                          "cell_id":table.cell_id,
                          "is_header": table.is_header,
                          "rowspan":   table.rowspan,
                          "merge_up":table.merge_up,
                          "merge_down":table.merge_down,
                          "col_id":table.col_id,
                          "text_lines":table.text_lines,
                        }

                page_results[-1]['elements'].append(element)

            print(f"Page {page_number}: Surya processing added to results.")

    except Exception as e:
        import traceback
        print(f"Error during Surya processing: {e}")
        traceback.print_exc()
        # Depending on desired behavior, you might return partial results or raise an error.
        # For now, raising an error if any Surya processing step fails for the batch.
        raise HTTPException(status_code=500, detail=f"Error processing document with Surya: {str(e)}")
    return {"filename": file.filename, "results": page_results}


@app.get("/health")
async def health_check():
    # Update health check for Surya predictors
    surya_loaded = bool(layout_predictor_surya and table_rec_predictor_surya)
    return {"status": "healthy", "surya_predictors_loaded": surya_loaded}



SERVICE_URL = "http://localhost:8000"
PDF_PATH = "/home/ji/ad1/doc_processing_service/app/overview.pdf" # Use the specified PDF path

@pytest.mark.asyncio
async def test_process_pdf_success():
    """Tests the /process_pdf/ endpoint with a valid PDF."""
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Test file not found at {PDF_PATH}")

    async with httpx.AsyncClient() as client:
        try:
            with open(PDF_PATH, "rb") as f:
                files = {"file": ("overview.pdf", f, "application/pdf")}
                response = await client.post(f"{SERVICE_URL}/process_pdf/", files=files, timeout=60.0) # Increased timeout

            print(f"Response Status Code: {response.status_code}")
            print(f"Response Body: {response.text[:500]}...") # Print first 500 chars of body

            assert response.status_code == 200
            response_json = response.json()
            assert "filename" in response_json
            assert response_json["filename"] == "overview.pdf"
            assert "results" in response_json
            assert isinstance(response_json["results"], list)
            assert len(response_json["results"]) > 0 # Assuming the PDF has at least one page

            # Optional: Add more specific assertions about the structure of results
            # For example, check if each page result has 'page_number' and 'elements'
            for page_result in response_json["results"]:
                assert "page_number" in page_result
                assert "elements" in page_result
                assert isinstance(page_result["elements"], list)

        except httpx.ConnectError as e:
            pytest.fail(f"Could not connect to service at {SERVICE_URL}. Is the service running? Error: {e}")
        except Exception as e:
            pytest.fail(f"An unexpected error occurred during the test: {e}")

