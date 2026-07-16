# You can symlink this script and it will navigate into the proper directory
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

cd "$SCRIPT_DIR" || exit 1

if [ ! -d "venv" ]; then
    echo "Venv not set up, respond [y] to setup and install requirements"
    read response
    if [ "$response" != "y" ]; then
        echo "Quitting"
        exit 0
    fi
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

source venv/bin/activate
echo "Starting up"
uvicorn server:app --port 8787 # For development go --reload

