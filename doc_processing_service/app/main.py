from fastapi import FastAPI, File, UploadFile, HTTPException
from PIL import Image
import pdf2image
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
import torch
import io
from typing import List, Dict, Any
import pytesseract

app = FastAPI()

# Load Model and Processor
# Note: apply_ocr=False means the processor expects words and boxes to be provided if the model needs them.
# If the goal is to perform OCR directly with the processor (using Tesseract), apply_ocr should be True,
# and Tesseract needs to be installed in the Docker image.
# For this iteration, we are attempting to extract text from token classifications, which is experimental for OCR.
try:
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=True) # Changed to True
    model = LayoutLMv3ForTokenClassification.from_pretrained("microsoft/layoutlmv3-base")
    model.eval() # Set model to evaluation mode
except Exception as e:
    print(f"Error loading model or processor: {e}")
    # Depending on policy, you might want to raise an exception here to stop the app from starting
    # or allow it to start and fail on endpoint usage.
    processor = None
    model = None

@app.post("/process_pdf/")
async def process_pdf_endpoint(file: UploadFile = File(...)):
    if not processor or not model:
        raise HTTPException(status_code=503, detail="Model or processor not available. Check server logs.")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF is accepted.")

    try:
        pdf_bytes = await file.read()
        images = pdf2image.convert_from_bytes(pdf_bytes)
    except Exception as e:
        # Log the exception for more details on the server side
        print(f"Error converting PDF to images: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read or convert PDF: {str(e)}")
    print(f"Converted PDF to {len(images)} images.")
    results = []
    for i, pil_image in enumerate(images):
        print(f"Processing page {i + 1}...")
        page_number = i + 1
        try:

            image = pil_image.convert("RGB")
            print(f"Processing page {page_number}...")  
            # Process image for the model
            # For LayoutLMv3ForTokenClassification, we usually pass the image and get token classifications.
            # No explicit "question" is typically used unless it's a QA model.
            encoding = processor(image, return_tensors="pt", truncation=True, padding="max_length", max_length=512)
            # print(f"Encoding for page {page_number}: {encoding}") # Can be very verbose
            
            # --- Get OCR'd text directly from the processor's output --- 
            # The input_ids from the encoding are the token IDs of the OCR'd text
            ocr_token_ids = encoding['input_ids'][0]
            extracted_text = processor.tokenizer.decode(ocr_token_ids, skip_special_tokens=True)
            # Log a snippet of the extracted text to verify
            print(f"Extracted text for page {page_number} (length: {len(extracted_text)}): {extracted_text[:500]}...")

            # --- Token Classification (Optional based on use case) ---
            # If you need to understand the role/type of each token (e.g., header, paragraph, custom entities),
            # then you would use the model's output. For just getting all text, the above is sufficient.
            #
            # with torch.no_grad():
            #     outputs = model(**encoding)
            # # print(f"Model outputs for page {page_number}: {outputs}") # Can be verbose
            # if hasattr(outputs, 'logits'):
            #     token_class_predictions = torch.argmax(outputs.logits, dim=2)
            #     predicted_class_ids = token_class_predictions[0].tolist()
            #     # print(f"Predicted token CLASS IDs for page {page_number}: {predicted_class_ids}")
            #     # Here you would typically map these class IDs to their labels (e.g., 'B-QUESTION', 'I-ANSWER')
            #     # and use this information in conjunction with the ocr_token_ids or extracted_text.
            #     # For example, to extract only text segments belonging to a certain class.
            #     pass # Placeholder for logic using token classifications

            results.append({
                "page_number": page_number,
                "extracted_text": extracted_text.strip(),
            })
            print(f"Extracted text for page {page_number}: {extracted_text.strip()}")
        except Exception as e:
            # Log the exception for more details on the server side
            print(f"Error processing page {page_number}: {e}")
            results.append({
                "page_number": page_number,
                "error": f"Failed to process page {page_number}: {str(e)}"
            })

    return {"filename": file.filename, "results": results}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "model_loaded": bool(model and processor)}
