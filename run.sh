set -o allexport
source .env
set +o allexport

pipenv run python chatbot.py leafwind $TWITCH_TOKEN

