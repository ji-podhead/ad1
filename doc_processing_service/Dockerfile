FROM python:3.9-slim

WORKDIR /app

# Install system dependencies required by pdf2image (poppler) and potentially other libraries
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY ./app/requirements.txt /app/requirements.txt
# Consider using --no-cache-dir to reduce layer size if not debugging package issues
RUN pip install -r requirements.txt

# COPY ./app /app

# To download model files during build time (optional):
# This makes the Docker image larger but can make the first startup of the container faster
# as it won't need to download models then. Ensure the user running this has network access
# and permissions to write to the Hugging Face cache dir (default ~/.cache/huggingface)
# or set TRANSFORMERS_CACHE to a path within /app that will be part of the image.
# ENV TRANSFORMERS_CACHE=/app/models_cache
# RUN python -c "from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification; \
#                LayoutLMv3Processor.from_pretrained('microsoft/layoutlmv3-base', cache_dir=os.environ.get('TRANSFORMERS_CACHE')); \
#                LayoutLMv3ForTokenClassification.from_pretrained('microsoft/layoutlmv3-base', cache_dir=os.environ.get('TRANSFORMERS_CACHE'))"
# For now, model download at build time is commented out to keep initial builds faster.
# The model will be downloaded on the first run of the application if not cached.
