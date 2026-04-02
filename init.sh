#!/bin/bash
set -e

echo "Setting up Terra Project development environment..."

# Create virtual environment if it doesn't already exist
if [ ! -d "terra_env" ]; then
    python3 -m venv terra_env
    echo "Virtual environment created."
else
    echo "Virtual environment already exists, skipping creation."
fi

# Activate virtual environment
source terra_env/bin/activate

# Install/upgrade dependencies
pip3 install --upgrade pip --quiet
pip3 install -r requirements.txt

# Register the Jupyter kernel (user-level, so VS Code and Jupyter can find it)
python3 -m ipykernel install --user --name=terra_kernel --display-name "Terra Project"

echo ""
echo "Setup complete. Next steps:"
echo "  1. In VS Code, install recommended extensions when prompted (Jupyter, Python)."
echo "  2. Open a notebook, click 'Select Kernel' > 'Jupyter Kernel' > 'Terra Project'."
