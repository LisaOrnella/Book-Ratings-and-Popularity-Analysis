import os
from dotenv import load_dotenv

load_dotenv()
key = os.environ.get("GROQ_API_KEY", "NOT FOUND")
print("GROQ_API_KEY:", key)