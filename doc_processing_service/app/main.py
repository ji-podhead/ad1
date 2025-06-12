from fastapi import FastAPI, File, UploadFile, HTTPException
from PIL import Image
import pdf2image
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
import torch
import io
from typing import List, Dict, Any

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
            print(f"Encoding for page {page_number}: {encoding}")
            # Model inference
            with torch.no_grad():
                outputs = model(**encoding)
            print(f"Model outputs for page {page_number}: {outputs}")
            # Post-process to get text from token classifications
            extracted_text = ""
            if hasattr(outputs, 'logits'):
                token_predictions = torch.argmax(outputs.logits, dim=2)
                # Each item in token_predictions[0] is a token ID for
                # hat position
                print(f"Token predictions for page {page_number}: {token_predictions}")
                predicted_token_ids = token_predictions[0].tolist()
                print(f"Predicted token IDs for page {page_number}: {predicted_token_ids}")
                # Filter out special tokens before converting to string
                # This depends on the tokenizer's special token IDs (e.g., pad_token_id)
                # Using tokenizer.decode is generally more robust for this.
                # However, processor.tokenizer.decode might also strip special tokens by default.

                # Get the tokens for the predicted IDs, excluding special ones.
                # The input_ids from encoding include special tokens. We only want to decode the non-special ones.
                # A common way is to use the input_ids from the encoding to know which tokens are actual content.
                input_ids = encoding['input_ids'][0].tolist()
                valid_token_indices = [idx for idx, token_id in enumerate(input_ids) if token_id not in processor.tokenizer.all_special_ids]

                filtered_predicted_token_ids = [predicted_token_ids[idx] for idx in valid_token_indices]

                extracted_text = processor.tokenizer.decode(filtered_predicted_token_ids, skip_special_tokens=True)

            else:
                extracted_text = f"Could not extract text from page {page_number}. Model output structure not as expected."

            results.append({
                "page_number": page_number,
                "extracted_text": extracted_text.strip(),
            })
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
