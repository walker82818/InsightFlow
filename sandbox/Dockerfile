# InsightFlow Python execution sandbox.
# Minimal, isolated image for running LLM-generated data-analysis code.
# Network is disabled at runtime (docker run --network=none); only the dataset
# is mounted read-only and a scratch volume is mounted read-write.
FROM python:3.12-slim

# Install numpy/pandas for statistics & modeling. Keep the image lean.
RUN pip install --no-cache-dir pandas==2.2.3 numpy==2.1.3

WORKDIR /work
COPY runner.py /work/runner.py

# Run as a non-root user for defense in depth.
RUN useradd -m runner && chown -R runner:runner /work
USER runner

ENTRYPOINT ["python", "/work/runner.py"]
