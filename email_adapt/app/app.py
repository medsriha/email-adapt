from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from email_adapt.gmail.src.initial_handshake import InitialHandshake
from email_adapt.gmail.src.utils.validation import validate_gmail_email
from urllib.parse import quote_plus
from pathlib import Path
import json
import os
import logging

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN_DIR = f"{Path(__file__).parent.parent.parent.parent}/credentials"

# Configure CORS with specific origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://pceiolcjjcninpkppmkimcjiincjjdjg",  # Your extension ID
        "http://localhost:8000",  # For local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

class EmailRequest(BaseModel):
    email: str
    token: str

class LogoutRequest(BaseModel):
    email: str

@app.post("/store-gmail-token")
async def store_gmail_token(request: EmailRequest):

    email = request.email
    validate_gmail_email(email)
    safe_email = quote_plus(email)

    try:
        # Create directory if it doesn't exist
        token_dir = f"{TOKEN_DIR}/{safe_email}"
        os.makedirs(token_dir, exist_ok=True)
        
        # Encrypt token before storing
        token_data = request.token
        
        with open(f"{token_dir}/token.json", 'w') as f:
            json.dump(token_data, f)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store token: {str(e)}")

@app.post("/connect-gmail")
async def connect_gmail(request: EmailRequest):
    try:
        handshake = InitialHandshake(email_address=request.email)
        handshake()
        return {"status": "success", "message": "Gmail connection and analysis complete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/logout-gmail")
async def logout_gmail(request: LogoutRequest):

    try:
        email = request.email 
        token_path = f"{TOKEN_DIR}/{quote_plus(email)}/token.json"
        
        if os.path.exists(token_path):
            os.remove(token_path)
            logger.info(f"Token removed for email: {email}")
            
        return {"status": "success", "message": "Successfully logged out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))