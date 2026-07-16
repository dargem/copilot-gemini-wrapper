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
uvicorn server:app --reload --port 8787

