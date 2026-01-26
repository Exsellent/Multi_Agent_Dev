#!/bin/bash
# generate-diagrams.sh

cd docs/diagrams

# Генерация PNG из PlantUML
plantuml -tpng architecture.puml
plantuml -tpng pipeline.puml
plantuml -tpng mcp-sequence.puml

echo "✅ Diagrams generated successfully"