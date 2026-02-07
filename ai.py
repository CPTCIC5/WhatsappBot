from openai import OpenAI
from dotenv import load_dotenv
import os


load_dotenv()
api = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api)
model = "gpt-5"


def chat_with_assistant(content):
    resp = client.responses.create(
        model = model,
        input=[
            {
                "role":"developer", "content": "You are a human like assistant skilled in general task like alexa and google cloud. You dont have to reply in more than 20 words unless asks for. Act more like human, talk casually as you can."
            },
            {
                "role":"user",
                "content": content
            }
        ],
        tools=[
            {
            "type": "web_search",
            "filters": {
              "allowed_domains": [
                  "ridra.in"
              ]}
            },
            {
                "type": "file_search",
                "vector_store_ids": [""]
            }
        ]
    )
    return resp.output_text