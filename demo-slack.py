"""
pip install slack-sdk
"""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Replace your_bot_token with the token you obtained in step 2
slack_token = "xoxb-4851507599-5236022417617-GwZ6R2p5YgCNuJAtRrCpXXkb"
client = WebClient(token=slack_token)

try:
    # Replace 'your_channel_id' with the ID or name of the channel you want to send a message to
    response = client.chat_postMessage(channel="#automation", text="Hello, world!")
    print(response)
except SlackApiError as e:
    print(f"Error sending message: {e}")
