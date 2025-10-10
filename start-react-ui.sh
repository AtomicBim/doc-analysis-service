#!/bin/bash

echo "===================================="
echo "Starting Doc Analysis React UI"
echo "===================================="
echo ""
echo "Starting API and React UI containers..."
echo "This may take a few minutes on first run."
echo ""
docker-compose up --build doc-analysis-api doc-analysis-ui-react

