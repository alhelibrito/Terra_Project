#!/bin/bash
set -e

echo "Setting up Terra Project development environment..."

# Create virtual environment if it doesn't already exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists, skipping creation."
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade dependencies
pip3 install --upgrade pip --quiet
pip3 install -r requirements.txt

# Register the Jupyter kernel (user-level, so VS Code and Jupyter can find it)
python3 -m ipykernel install --user --name=terra_kernel --display-name "Terra Project"

# Automatically strip output from notebooks before committing to version control
nbstripout --install

# Configure nbdime for better notebook diffing in git
nbdime config-git --enable --global

# Set up pre-commit hooks for code quality and consistency
pre-commit install

echo ""
echo "Setup complete. Next steps:"
echo "  1. In VS Code, install recommended extensions when prompted (Jupyter, Python)."
echo "  2. Open a notebook, click 'Select Kernel' > 'Python Environments' > 'venv'"
